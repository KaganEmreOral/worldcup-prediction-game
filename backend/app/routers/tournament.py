from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Group, Match, Stadium, Team, Tournament
from app.seeds.tournament_loader import get_active_tournament

router = APIRouter(prefix="/api/tournament", tags=["tournament"])


@router.get("/active")
async def get_active(db: AsyncSession = Depends(get_db)):
    tournament = await get_active_tournament(db)
    if not tournament:
        return None
    return {
        "id": tournament.id,
        "slug": tournament.slug,
        "name": tournament.name,
        "year": tournament.year,
        "format_type": tournament.format_type,
        "starts_at": tournament.starts_at.isoformat() if tournament.starts_at else None,
        "ends_at": tournament.ends_at.isoformat() if tournament.ends_at else None,
        "format_config": tournament.format_config,
    }


@router.get("/groups")
async def get_groups(db: AsyncSession = Depends(get_db)):
    tournament = await get_active_tournament(db)
    if not tournament:
        return []
    result = await db.execute(
        select(Group).where(Group.tournament_id == tournament.id).order_by(Group.display_order)
    )
    groups = result.scalars().all()
    teams_result = await db.execute(select(Team).where(Team.tournament_id == tournament.id))
    teams = teams_result.scalars().all()
    teams_by_group: dict[str, list] = {}
    for t in teams:
        if t.group_name:
            teams_by_group.setdefault(t.group_name, []).append({
                "id": t.id,
                "name": t.name,
                "code": t.code,
                "flag_code": t.flag_code,
                "confederation": t.confederation,
                "position": t.group_position,
            })
    return [
        {"name": g.name, "display_order": g.display_order, "teams": teams_by_group.get(g.name, [])}
        for g in groups
    ]


@router.get("/settings")
async def public_settings(db: AsyncSession = Depends(get_db)):
    from app.models import TournamentSettings

    tournament = await get_active_tournament(db)
    if not tournament:
        return {"predictions_locked": False, "tournament_started": False}
    result = await db.execute(
        select(TournamentSettings).where(TournamentSettings.tournament_id == tournament.id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        return {"predictions_locked": False, "tournament_started": False}
    return {
        "predictions_locked": settings.predictions_locked,
        "tournament_started": settings.tournament_started,
        "actual_top_scorer": settings.actual_top_scorer,
        "actual_top_assister": settings.actual_top_assister,
    }
