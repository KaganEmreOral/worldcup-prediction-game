"""Per-user simulated World Cup universe — full group + knockout tree."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    GroupStandingsCache,
    KnockoutBracketCache,
    KnockoutPrediction,
    Match,
    MatchStage,
    UserKnockoutBracket,
)
from app.services.group_simulation import MatchResult, compute_group_standings, rank_third_place_teams
from app.services.knockout_generator import build_knockout_tree, generate_r32_bracket
from app.services.scoring_engine import simulate_user_groups
from app.services.tournament_config import get_knockout_rules

logger = logging.getLogger(__name__)

STAGES_ORDER = ("R32", "R16", "QF", "SF", "F")


def _preds_by_slot(knockout_preds: dict[str, tuple[int, int]]) -> tuple[dict, dict, dict, dict, dict]:
    r32, r16, qf, sf, final = {}, {}, {}, {}, {}
    for slot, scores in knockout_preds.items():
        if slot.startswith("R32"):
            r32[slot] = scores
        elif slot.startswith("R16"):
            r16[slot] = scores
        elif slot.startswith("QF"):
            qf[slot] = scores
        elif slot.startswith("SF"):
            sf[slot] = scores
        elif slot.startswith("F"):
            final[slot] = scores
    return r32, r16, qf, sf, final


def _state_hash(predictions: dict[int, tuple[int, int]]) -> str:
    payload = json.dumps(sorted((str(k), v) for k, v in predictions.items()), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def validate_tree_no_tbd(tree: dict, *, strict: bool = True) -> None:
    """Raise if any knockout fixture lacks both teams."""
    missing: list[str] = []
    for stage in STAGES_ORDER:
        for m in tree.get(stage, []):
            ta = m.get("team_a")
            tb = m.get("team_b")
            if not ta or not tb or not ta.get("id") or not tb.get("id"):
                missing.append(m.get("label", "?"))
    if missing and strict:
        raise ValueError(f"Knockout tree incomplete (TBD): {missing[:8]}{'...' if len(missing) > 8 else ''}")


def build_user_tournament_tree(
    teams_by_group: dict[str, list[tuple[int, str, str]]],
    group_matches: list[Match],
    group_predictions: dict[int, tuple[int, int]],
    knockout_preds: dict[str, tuple[int, int]],
    rules: dict,
    *,
    allow_placeholder_winners: bool = False,
) -> tuple[dict, dict[str, list[dict]], dict[str, list]]:
    """
    Returns (qualifiers, full_tree, standings_by_group).
    When allow_placeholder_winners=True, unset KO scores advance team_a for display only.
    """
    user_qualifiers = simulate_user_groups(teams_by_group, group_predictions, group_matches)
    if not user_qualifiers:
        raise ValueError("Could not simulate group standings from predictions")

    all_standings: dict[str, list] = {}
    standings_objs = {}
    for group_name, team_list in teams_by_group.items():
        results = []
        for m in group_matches:
            if m.group_name == group_name and m.id in group_predictions:
                sa, sb = group_predictions[m.id]
                results.append(MatchResult(m.team_a_id, m.team_b_id, sa, sb))
        if results:
            st = compute_group_standings(team_list, results)
            standings_objs[group_name] = st
            all_standings[group_name] = [s.to_dict() for s in st]
    third_ranked = rank_third_place_teams(standings_objs)

    r32 = generate_r32_bracket(user_qualifiers, third_ranked, rules)
    r32p, r16p, qfp, sfp, finalp = _preds_by_slot(knockout_preds)
    tree = build_knockout_tree(
        r32,
        rules,
        r32_preds=r32p,
        r16_preds=r16p,
        qf_preds=qfp,
        sf_preds=sfp,
        final_pred=finalp,
        allow_placeholder_winners=allow_placeholder_winners,
    )
    return user_qualifiers, tree, all_standings


async def persist_user_tournament_state(
    db: AsyncSession,
    user_id: int,
    group_matches: list[Match],
    knockout_matches: list[Match],
    group_predictions: dict[int, tuple[int, int]],
    knockout_preds: dict[str, tuple[int, int]],
    teams_by_group: dict,
) -> dict:
    """Store per-user standings, full KO tree snapshot, and resolved bracket rows."""
    rules = await get_knockout_rules(db)
    qualifiers, tree, standings_by_group = build_user_tournament_tree(
        teams_by_group,
        group_matches,
        group_predictions,
        knockout_preds,
        rules,
        allow_placeholder_winners=False,
    )
    validate_tree_no_tbd(tree, strict=True)

    state_hash = _state_hash(group_predictions)
    slot_to_match = {m.bracket_slot: m for m in knockout_matches if m.bracket_slot}

    await db.execute(delete(GroupStandingsCache).where(GroupStandingsCache.user_id == user_id))
    for group_name, standings in standings_by_group.items():
        db.add(
            GroupStandingsCache(
                user_id=user_id,
                group_name=group_name,
                standings_json=standings,
                qualified_teams=qualifiers.get(group_name, []),
            )
        )

    await db.execute(delete(KnockoutBracketCache).where(KnockoutBracketCache.user_id == user_id))
    for stage_key in STAGES_ORDER:
        if tree.get(stage_key):
            db.add(
                KnockoutBracketCache(
                    user_id=user_id,
                    stage=MatchStage(stage_key),
                    bracket_json={"matches": tree[stage_key], "state_hash": state_hash},
                )
            )

    await db.execute(delete(UserKnockoutBracket).where(UserKnockoutBracket.user_id == user_id))
    for stage_key in STAGES_ORDER:
        for m in tree.get(stage_key, []):
            slot = m["label"]
            canon = slot_to_match.get(slot)
            ta = m.get("team_a") or {}
            tb = m.get("team_b") or {}
            scores = knockout_preds.get(slot, (0, 0))
            db.add(
                UserKnockoutBracket(
                    user_id=user_id,
                    match_id=canon.id if canon else None,
                    bracket_slot=slot,
                    stage=MatchStage(stage_key),
                    match_number=m.get("match_number"),
                    team_a_id=ta["id"],
                    team_b_id=tb["id"],
                    predicted_score_a=scores[0],
                    predicted_score_b=scores[1],
                    source_group_state_hash=state_hash,
                    updated_at=datetime.now(timezone.utc),
                )
            )

    ko_result = await db.execute(
        select(KnockoutPrediction).where(KnockoutPrediction.user_id == user_id)
    )
    for kp in ko_result.scalars():
        for stage_key in STAGES_ORDER:
            for m in tree.get(stage_key, []):
                if m["label"] == kp.bracket_slot:
                    ta, tb = m.get("team_a") or {}, m.get("team_b") or {}
                    kp.sim_team_a_id = ta.get("id")
                    kp.sim_team_b_id = tb.get("id")
                    break

    logger.info(
        "user_tournament.persisted user_id=%s slots=%s hash=%s",
        user_id,
        sum(len(tree.get(s, [])) for s in STAGES_ORDER),
        state_hash,
    )
    return {"qualifiers": qualifiers, "bracket": tree, "state_hash": state_hash}


async def load_user_bracket_tree(db: AsyncSession, user_id: int) -> dict | None:
    """Load cached per-user knockout tree from DB."""
    result = await db.execute(
        select(KnockoutBracketCache).where(KnockoutBracketCache.user_id == user_id)
    )
    rows = result.scalars().all()
    if not rows:
        return None
    tree: dict = {}
    for row in rows:
        tree[row.stage.value] = row.bracket_json.get("matches", [])
    return tree
