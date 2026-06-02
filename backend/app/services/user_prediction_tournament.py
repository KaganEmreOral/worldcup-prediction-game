"""
Universe A — user prediction tournament (simulated from predicted group scores).

Used ONLY for:
- collecting knockout predictions along the user's simulated path
- deriving which teams the user believes reach each round

Never used as scoring truth.
"""

from __future__ import annotations

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
from app.services.group_simulation import (
    MatchResult,
    compute_group_standings,
    get_qualified_teams,
    rank_third_place_teams,
)
from app.services.bracket_participants import STAGES, champion_team_id, teams_in_round
from app.services.knockout_generator import build_knockout_tree, generate_r32_bracket, validate_r32_bracket
from app.services.tournament_config import get_knockout_rules


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


def validate_bracket_no_tbd(bracket_tree: dict, *, stages: tuple[str, ...] = STAGES) -> None:
    missing: list[str] = []
    for stage in stages:
        for m in bracket_tree.get(stage, []):
            ta, tb = m.get("team_a"), m.get("team_b")
            if not ta or not tb or not ta.get("id") or not tb.get("id"):
                missing.append(m.get("label", "?"))
    if missing:
        raise ValueError(f"User prediction bracket incomplete: {missing[:8]}")


def build_user_prediction_tournament(
    teams_by_group: dict[str, list[tuple[int, str, str]]],
    group_matches: list[Match],
    group_predictions: dict[int, tuple[int, int]],
    knockout_predictions: dict[str, tuple[int, int]],
    rules: dict,
    *,
    allow_placeholder_winners: bool = False,
) -> tuple[dict[str, list], dict, dict[str, list]]:
    """
    Full simulated bracket from user group predictions + user KO score picks.
    Returns (qualifiers, bracket_tree, standings_by_group).
    """
    if len(teams_by_group) != 12:
        raise ValueError(f"Expected 12 groups, got {len(teams_by_group)}")

    standings_objs = {}
    all_standings: dict[str, list] = {}
    for group_name, team_list in teams_by_group.items():
        results = []
        for m in group_matches:
            if m.group_name == group_name and m.id in group_predictions:
                sa, sb = group_predictions[m.id]
                results.append(MatchResult(m.team_a_id, m.team_b_id, sa, sb))
        if not results:
            raise ValueError(f"Group {group_name} has no predicted match results")
        st = compute_group_standings(team_list, results)
        standings_objs[group_name] = st
        all_standings[group_name] = [s.to_dict() for s in st]

    qualifiers = get_qualified_teams(standings_objs, num_best_third=rules.get("best_third_count", 8))
    third_ranked = rank_third_place_teams(standings_objs)
    r32 = generate_r32_bracket(qualifiers, third_ranked, rules)
    validate_r32_bracket(r32)

    r32p, r16p, qfp, sfp, finalp = _preds_by_slot(knockout_predictions)
    bracket_tree = build_knockout_tree(
        r32,
        rules,
        r32_preds=r32p,
        r16_preds=r16p,
        qf_preds=qfp,
        sf_preds=sfp,
        final_pred=finalp,
        allow_placeholder_winners=allow_placeholder_winners,
    )
    if not allow_placeholder_winners:
        validate_bracket_no_tbd(bracket_tree)
    return qualifiers, bracket_tree, all_standings


async def load_user_prediction_tournament(db: AsyncSession, user_id: int) -> dict | None:
    """Load cached user prediction bracket tree (Universe A snapshot)."""
    result = await db.execute(select(KnockoutBracketCache).where(KnockoutBracketCache.user_id == user_id))
    rows = result.scalars().all()
    if not rows:
        return None
    tree: dict = {}
    for row in rows:
        tree[row.stage.value] = row.bracket_json.get("matches", [])
    return tree


async def persist_user_prediction_tournament(
    db: AsyncSession,
    user_id: int,
    group_matches: list[Match],
    knockout_matches: list[Match],
    group_predictions: dict[int, tuple[int, int]],
    knockout_predictions: dict[str, tuple[int, int]],
    teams_by_group: dict,
    *,
    state_hash: str | None = None,
) -> dict:
    """Persist Universe A snapshot after prediction submit."""
    import hashlib
    import json
    from datetime import datetime, timezone

    rules = await get_knockout_rules(db)
    qualifiers, bracket_tree, standings_by_group = build_user_prediction_tournament(
        teams_by_group,
        group_matches,
        group_predictions,
        knockout_predictions,
        rules,
        allow_placeholder_winners=False,
    )

    if state_hash is None:
        payload = json.dumps(sorted((str(k), v) for k, v in group_predictions.items()), sort_keys=True)
        state_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]

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
    for stage_key in STAGES:
        if bracket_tree.get(stage_key):
            db.add(
                KnockoutBracketCache(
                    user_id=user_id,
                    stage=MatchStage(stage_key),
                    bracket_json={"matches": bracket_tree[stage_key], "state_hash": state_hash},
                )
            )

    await db.execute(delete(UserKnockoutBracket).where(UserKnockoutBracket.user_id == user_id))
    for stage_key in STAGES:
        for m in bracket_tree.get(stage_key, []):
            slot = m["label"]
            canon = slot_to_match.get(slot)
            ta, tb = m.get("team_a") or {}, m.get("team_b") or {}
            scores = knockout_predictions.get(slot, (0, 0))
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

    ko_result = await db.execute(select(KnockoutPrediction).where(KnockoutPrediction.user_id == user_id))
    for kp in ko_result.scalars():
        for stage_key in STAGES:
            for m in bracket_tree.get(stage_key, []):
                if m["label"] == kp.bracket_slot:
                    ta, tb = m.get("team_a") or {}, m.get("team_b") or {}
                    kp.sim_team_a_id = ta.get("id")
                    kp.sim_team_b_id = tb.get("id")
                    break

    return {
        "qualifiers": qualifiers,
        "bracket_tree": bracket_tree,
        "standings_by_group": standings_by_group,
        "state_hash": state_hash,
        "round_participants": {s: list(teams_in_round(bracket_tree, s)) for s in STAGES},
    }
