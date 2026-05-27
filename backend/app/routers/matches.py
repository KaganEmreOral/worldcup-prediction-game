from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user, get_optional_user
from app.database import get_db
from app.models import Match, MatchStage, Prediction, Team, User, UserScore
from app.seeds.tournament_loader import get_active_tournament

router = APIRouter(prefix="/api/matches", tags=["matches"])


def _enrich_match(m: Match) -> dict:
    return {
        "id": m.id,
        "stage": m.stage.value,
        "group_name": m.group_name,
        "team_a_id": m.team_a_id,
        "team_b_id": m.team_b_id,
        "team_a_name": m.team_a.name if m.team_a else None,
        "team_b_name": m.team_b.name if m.team_b else None,
        "team_a_code": m.team_a.code if m.team_a else None,
        "team_b_code": m.team_b.code if m.team_b else None,
        "team_a_flag": m.team_a.flag_code if m.team_a else None,
        "team_b_flag": m.team_b.flag_code if m.team_b else None,
        "real_score_a": m.real_score_a,
        "real_score_b": m.real_score_b,
        "status": m.status.value,
        "bracket_slot": m.bracket_slot,
        "match_order": m.match_order,
        "match_number": m.match_number,
        "matchday": m.matchday,
        "kickoff_time_utc": m.kickoff_time_utc.isoformat() if m.kickoff_time_utc else None,
        "stadium": {
            "name": m.stadium.name,
            "city": m.stadium.city,
            "country": m.stadium.country,
        }
        if m.stadium
        else None,
    }


@router.get("")
async def list_matches(
    stage: str | None = None,
    group: str | None = None,
    matchday: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    tournament = await get_active_tournament(db)
    q = (
        select(Match)
        .options(
            selectinload(Match.team_a),
            selectinload(Match.team_b),
            selectinload(Match.stadium),
        )
        .order_by(Match.stage_order, Match.match_number, Match.id)
    )
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    if stage:
        q = q.where(Match.stage == stage)
    if group:
        q = q.where(Match.group_name == group)
    if matchday:
        q = q.where(Match.matchday == matchday)
    matches = (await db.execute(q)).scalars().all()

    user_preds = {}
    score_by_match: dict[int, dict] = {}
    if user:
        pred_result = await db.execute(select(Prediction).where(Prediction.user_id == user.id))
        user_preds = {p.match_id: (p.predicted_score_a, p.predicted_score_b) for p in pred_result.scalars()}
        us_result = await db.execute(select(UserScore).where(UserScore.user_id == user.id))
        us = us_result.scalar_one_or_none()
        if us and us.breakdown_json:
            for ms in us.breakdown_json.get("match_scores", []):
                if mid := ms.get("match_id"):
                    score_by_match[mid] = ms

    out = []
    for m in matches:
        item = {
            **_enrich_match(m),
            "prediction": {"score_a": user_preds[m.id][0], "score_b": user_preds[m.id][1]}
            if m.id in user_preds
            else None,
        }
        if m.id in score_by_match:
            item["scoring"] = score_by_match[m.id]
        out.append(item)
    return out


@router.get("/teams")
async def list_teams(db: AsyncSession = Depends(get_db)):
    tournament = await get_active_tournament(db)
    q = select(Team).order_by(Team.group_name, Team.group_position)
    if tournament:
        q = q.where(Team.tournament_id == tournament.id)
    teams = (await db.execute(q)).scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "code": t.code,
            "group_name": t.group_name,
            "flag_code": t.flag_code,
            "confederation": t.confederation,
        }
        for t in teams
    ]
