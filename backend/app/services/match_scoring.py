"""Event-driven scoring when admin enters real match results."""

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, MatchStatus, UserMatchScore
from app.services.recalculation import recalculate_all

logger = logging.getLogger(__name__)


def is_scorable_result(match: Match) -> bool:
    """Match has a complete real result suitable for scoring."""
    return (
        match.real_score_a is not None
        and match.real_score_b is not None
        and match.status == MatchStatus.FINISHED
    )


async def on_match_result_updated(
    db: AsyncSession,
    match: Match,
    *,
    trigger: str = "admin",
) -> dict:
    """
    Idempotent full recomputation triggered by a match result change.
    Admin match results are the only source of truth.
    """
    if match.real_score_a is None or match.real_score_b is None:
        logger.info(
            "scoring.skip match_id=%s trigger=%s reason=incomplete_scores",
            match.id,
            trigger,
        )
        return {"scored": False, "reason": "incomplete_scores"}

    if match.status != MatchStatus.FINISHED:
        match.status = MatchStatus.FINISHED

    logger.info(
        "scoring.trigger match_id=%s stage=%s group=%s score=%s-%s trigger=%s",
        match.id,
        match.stage.value,
        match.group_name,
        match.real_score_a,
        match.real_score_b,
        trigger,
    )

    result = await recalculate_all(db, trigger_match_id=match.id, trigger_source=trigger)
    result["scored"] = True
    result["match_id"] = match.id

    logger.info(
        "scoring.complete match_id=%s users_scored=%s events=%s",
        match.id,
        result.get("users_scored", 0),
        len(result.get("recent_events", [])),
    )
    return result


async def sync_user_match_scores(
    db: AsyncSession,
    user_id: int,
    match_score_entries: list[dict],
) -> int:
    """Replace per-match score rows for one user (idempotent upsert via delete+insert)."""
    await db.execute(delete(UserMatchScore).where(UserMatchScore.user_id == user_id))
    now = datetime.now(timezone.utc)
    count = 0
    for entry in match_score_entries:
        match_id = entry.get("match_id")
        if not match_id:
            continue
        points = int(entry.get("points", 0))
        db.add(
            UserMatchScore(
                user_id=user_id,
                match_id=match_id,
                points_earned=points,
                breakdown_json=entry,
                updated_at=now,
            )
        )
        count += 1
    return count


async def verify_match_points_consistency(db: AsyncSession, user_id: int) -> bool:
    """Leaderboard match subtotal should equal sum of user_match_scores."""
    from app.models import UserScore

    us = await db.execute(select(UserScore).where(UserScore.user_id == user_id))
    row = us.scalar_one_or_none()
    if not row or not row.breakdown_json:
        return True
    ledger = await db.execute(
        select(UserMatchScore).where(UserMatchScore.user_id == user_id)
    )
    ledger_sum = sum(r.points_earned for r in ledger.scalars().all())
    match_entries = row.breakdown_json.get("match_scores", [])
    breakdown_sum = sum(int(m.get("points", 0)) for m in match_entries)
    return ledger_sum == breakdown_sum
