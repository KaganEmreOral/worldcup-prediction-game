from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user, get_optional_user
from app.database import get_db
from app.models import (
    GroupStandingsCache,
    LeaderboardSnapshot,
    Match,
    MatchStage,
    MatchStatus,
    Prediction,
    SpecialPrediction,
    Team,
    User,
    UserScore,
)
from app.schemas import LeaderboardEntry, UserScoreResponse
from app.services.cache import cached
from app.services.group_simulation import MatchResult, compute_group_standings
from app.seeds.tournament_loader import get_active_tournament

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@router.get("")
async def get_leaderboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserScore, User)
        .join(User, UserScore.user_id == User.id)
        .order_by(UserScore.total_score.desc())
    )
    rows = result.all()

    prev_result = await db.execute(
        select(LeaderboardSnapshot).order_by(LeaderboardSnapshot.snapshot_date.desc()).limit(1)
    )
    prev = prev_result.scalar_one_or_none()
    prev_ranks: dict[int, int] = {}
    prev_scores: dict[int, float] = {}
    if prev:
        for i, row in enumerate(prev.rankings_json):
            prev_ranks[row["user_id"]] = i + 1
            prev_scores[row["user_id"]] = row.get("total_score", 0)

    entries = []
    for rank, (score, user) in enumerate(rows, start=1):
        rank_change = prev_ranks.get(user.id, rank) - rank if user.id in prev_ranks else None
        daily = round(score.total_score - prev_scores.get(user.id, 0), 1) if user.id in prev_scores else score.total_score
        entries.append(
            LeaderboardEntry(
                user_id=user.id,
                name=user.name,
                username=user.username,
                total_score=score.total_score,
                group_score=float(score.group_score + score.qualification_score),
                knockout_score=float(score.knockout_score),
                special_score=float(score.special_score),
                rank=rank,
                rank_change=rank_change,
                daily_points=daily,
            )
        )
    return entries


@router.get("/events")
async def get_scoring_events(db: AsyncSession = Depends(get_db)):
    """Latest scoring events from user breakdowns."""
    result = await db.execute(
        select(UserScore, User).join(User, UserScore.user_id == User.id).order_by(UserScore.updated_at.desc())
    )
    events = []
    for score, user in result.all()[:50]:
        if not score.breakdown_json:
            continue
        for m in score.breakdown_json.get("match_scores", [])[:5]:
            if m.get("points", 0) > 0:
                events.append({**m, "user_name": user.name, "user_id": user.id})
    events.sort(key=lambda x: -x.get("points", 0))
    return events[:25]


@router.get("/daily")
async def get_daily_leaderboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LeaderboardSnapshot).order_by(LeaderboardSnapshot.snapshot_date.desc()).limit(30)
    )
    snapshots = result.scalars().all()
    return [{"date": s.snapshot_date.isoformat(), "rankings": s.rankings_json[:20]} for s in snapshots]


@router.get("/me")
async def get_my_score(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserScore).where(UserScore.user_id == user.id))
    score = result.scalar_one_or_none()
    if not score:
        return UserScoreResponse(
            user_id=user.id, name=user.name, group_score=0, qualification_score=0,
            knockout_score=0, special_score=0, chain_bonus=0, total_score=0, breakdown_json=None,
        )
    return UserScoreResponse(
        user_id=user.id, name=user.name, group_score=score.group_score,
        qualification_score=score.qualification_score, knockout_score=score.knockout_score,
        special_score=score.special_score, chain_bonus=score.chain_bonus,
        total_score=score.total_score, breakdown_json=score.breakdown_json,
    )


@router.get("/me/breakdown")
async def get_my_breakdown(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserScore).where(UserScore.user_id == user.id))
    score = result.scalar_one_or_none()
    if not score or not score.breakdown_json:
        return {"summary": {}, "match_scores": [], "other": []}
    bj = score.breakdown_json
    match_scores = sorted(bj.get("match_scores", []), key=lambda x: (x.get("stage", ""), x.get("match_number") or 0))
    other = bj.get("details", [])
    return {
        "summary": {k: bj[k] for k in bj if k not in ("details", "match_scores")},
        "match_scores": match_scores,
        "other": other,
    }


@router.get("/user/{user_id}")
async def get_user_score(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserScore, User).join(User, UserScore.user_id == User.id).where(UserScore.user_id == user_id)
    )
    row = result.first()
    if not row:
        return None
    score, user = row
    return UserScoreResponse(
        user_id=user.id, name=user.name, group_score=score.group_score,
        qualification_score=score.qualification_score, knockout_score=score.knockout_score,
        special_score=score.special_score, chain_bonus=score.chain_bonus,
        total_score=score.total_score, breakdown_json=score.breakdown_json,
    )


@router.get("/standings")
async def get_my_standings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GroupStandingsCache).where(GroupStandingsCache.user_id == user.id).order_by(GroupStandingsCache.group_name)
    )
    caches = result.scalars().all()
    return [
        {"group_name": c.group_name, "standings": c.standings_json, "qualified_teams": c.qualified_teams}
        for c in caches
    ]
