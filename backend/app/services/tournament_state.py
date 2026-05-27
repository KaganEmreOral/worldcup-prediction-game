"""Rebuild all derived tournament projections from database truth."""

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    GroupStandingsCache,
    KnockoutBracketCache,
    LeaderboardSnapshot,
    Match,
    MatchStatus,
    TournamentSettings,
    UserMatchScore,
    UserScore,
)
from app.seeds.tournament_loader import get_active_tournament
from app.services.cache import invalidate
from app.services.recalculation import recalculate_all

logger = logging.getLogger(__name__)


async def clear_derived_state(db: AsyncSession) -> None:
    """Remove computed scoring, standings caches, and leaderboard history."""
    await db.execute(delete(UserMatchScore))
    await db.execute(delete(GroupStandingsCache))
    await db.execute(delete(KnockoutBracketCache))
    await db.execute(delete(LeaderboardSnapshot))
    await db.execute(delete(UserScore))
    await db.flush()
    logger.info("derived_state.cleared")


async def recompute_tournament_state(
    db: AsyncSession,
    *,
    trigger_match_id: int | None = None,
    trigger_source: str = "recompute",
) -> dict:
    """
    Full rebuild: wipe projections, invalidate caches, recalculate from DB.
    Use after admin reset of match results or when derived data may be stale.
    """
    logger.info(
        "recompute_tournament_state.start source=%s match_id=%s",
        trigger_source,
        trigger_match_id,
    )
    invalidate(None)
    await clear_derived_state(db)
    result = await recalculate_all(
        db,
        trigger_match_id=trigger_match_id,
        trigger_source=trigger_source,
        skip_derived_clear=True,
    )
    result["recomputed"] = True
    logger.info(
        "recompute_tournament_state.done users_scored=%s leaderboard_entries=%s",
        result.get("users_scored", 0),
        len(result.get("leaderboard", [])),
    )
    return result


async def reset_all_match_results(db: AsyncSession) -> dict:
    """Clear real scores on all matches and rebuild derived state (fresh tournament)."""
    tournament = await get_active_tournament(db)
    q = select(Match)
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    matches = (await db.execute(q)).scalars().all()
    for m in matches:
        m.real_score_a = None
        m.real_score_b = None
        m.status = MatchStatus.SCHEDULED

    if tournament:
        settings_result = await db.execute(
            select(TournamentSettings).where(TournamentSettings.tournament_id == tournament.id)
        )
    else:
        settings_result = await db.execute(select(TournamentSettings).limit(1))
    settings = settings_result.scalar_one_or_none()
    if settings:
        settings.actual_top_scorer = None
        settings.actual_top_assister = None

    await db.flush()
    logger.info("match_results.reset count=%s", len(matches))

    recompute = await recompute_tournament_state(db, trigger_source="admin_reset_match_results")
    return {
        "message": f"Reset {len(matches)} match results",
        "matches_reset": len(matches),
        "recompute": recompute,
        "leaderboard": recompute.get("leaderboard", []),
    }
