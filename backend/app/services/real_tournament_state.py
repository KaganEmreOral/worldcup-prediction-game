"""
Universe B — real tournament (admin-entered group + knockout results).

Single source of truth for scoring. Never derived from user predictions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, MatchStage, RealTournamentState
from app.services.group_simulation import MatchResult, compute_group_standings, rank_third_place_teams
from app.services.knockout_generator import build_knockout_tree, generate_r32_bracket, validate_r32_bracket
from app.services.scoring_engine import simulate_real_groups
from app.services.bracket_participants import STAGES, champion_team_id, teams_in_round

logger = logging.getLogger(__name__)


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


def real_knockout_results_from_matches(knockout_matches: list[Match]) -> dict[str, tuple[int, int]]:
    """Admin-entered real scores keyed by canonical bracket_slot."""
    preds = {}
    for m in knockout_matches:
        if m.bracket_slot and m.real_score_a is not None and m.real_score_b is not None:
            preds[m.bracket_slot] = (m.real_score_a, m.real_score_b)
    return preds


def build_real_tournament_bracket(
    teams_by_group: dict,
    group_matches: list[Match],
    knockout_matches: list[Match],
    rules: dict,
) -> tuple[dict[str, list], dict]:
    """
    Build real knockout tree from admin group results + admin KO results.
    Returns (qualifiers, bracket_tree).
    """
    standings_objs = {}
    for group_name, team_list in teams_by_group.items():
        results = []
        for m in group_matches:
            if m.group_name == group_name and m.real_score_a is not None and m.real_score_b is not None:
                results.append(MatchResult(m.team_a_id, m.team_b_id, m.real_score_a, m.real_score_b))
        if results:
            standings_objs[group_name] = compute_group_standings(team_list, results)

    qualifiers = simulate_real_groups(teams_by_group, group_matches)
    if not qualifiers:
        return {}, {}

    third_ranked = rank_third_place_teams(standings_objs) if standings_objs else []
    r32 = generate_r32_bracket(qualifiers, third_ranked, rules)
    validate_r32_bracket(r32)

    ko_results = real_knockout_results_from_matches(knockout_matches)
    r32p, r16p, qfp, sfp, finalp = _preds_by_slot(ko_results)
    bracket_tree = build_knockout_tree(
        r32,
        rules,
        r32_preds=r32p,
        r16_preds=r16p,
        qf_preds=qfp,
        sf_preds=sfp,
        final_pred=finalp,
        allow_placeholder_winners=False,
    )
    return qualifiers, bracket_tree


async def persist_real_tournament_state(
    db: AsyncSession,
    tournament_id: int,
    teams_by_group: dict,
    group_matches: list[Match],
    knockout_matches: list[Match],
    rules: dict,
) -> RealTournamentState | None:
    """Upsert Universe B snapshot after admin updates real results."""
    qualifiers, bracket_tree = build_real_tournament_bracket(
        teams_by_group, group_matches, knockout_matches, rules
    )
    if not bracket_tree:
        return None

    participants = {s: list(teams_in_round(bracket_tree, s)) for s in STAGES}
    champion_id = champion_team_id(bracket_tree)

    result = await db.execute(
        select(RealTournamentState).where(RealTournamentState.tournament_id == tournament_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        row = RealTournamentState(tournament_id=tournament_id)
        db.add(row)

    row.qualifiers_json = qualifiers
    row.bracket_json = bracket_tree
    row.round_participants_json = participants
    row.champion_team_id = champion_id
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    logger.info(
        "real_tournament_state.persisted tournament_id=%s r32_teams=%s champion=%s",
        tournament_id,
        len(participants.get("R32", [])),
        champion_id,
    )
    return row


async def load_real_tournament_state(db: AsyncSession, tournament_id: int) -> dict | None:
    """Load cached real bracket tree, or None if not built yet."""
    result = await db.execute(
        select(RealTournamentState).where(RealTournamentState.tournament_id == tournament_id)
    )
    row = result.scalar_one_or_none()
    if not row or not row.bracket_json:
        return None
    return row.bracket_json


async def load_real_tournament_snapshot(db: AsyncSession, tournament_id: int) -> RealTournamentState | None:
    result = await db.execute(
        select(RealTournamentState).where(RealTournamentState.tournament_id == tournament_id)
    )
    return result.scalar_one_or_none()
