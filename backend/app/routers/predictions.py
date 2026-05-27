from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import KnockoutPrediction, Match, MatchStage, Prediction, SpecialPrediction, TournamentSettings, User
from app.schemas import PredictionBulkSubmit

from app.seeds.tournament_loader import get_active_tournament

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


async def _check_locked(db: AsyncSession):
    tournament = await get_active_tournament(db)
    if tournament:
        result = await db.execute(
            select(TournamentSettings).where(TournamentSettings.tournament_id == tournament.id)
        )
    else:
        result = await db.execute(select(TournamentSettings).limit(1))
    settings = result.scalar_one_or_none()
    if settings and settings.predictions_locked:
        raise HTTPException(status_code=403, detail="Predictions are locked")


@router.get("")
async def get_my_predictions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Prediction).where(Prediction.user_id == user.id))
    preds = result.scalars().all()
    ko_result = await db.execute(select(KnockoutPrediction).where(KnockoutPrediction.user_id == user.id))
    ko_preds = ko_result.scalars().all()
    sp_result = await db.execute(select(SpecialPrediction).where(SpecialPrediction.user_id == user.id))
    sp = sp_result.scalar_one_or_none()
    return {
        "predictions": [
            {"match_id": p.match_id, "predicted_score_a": p.predicted_score_a, "predicted_score_b": p.predicted_score_b}
            for p in preds
        ],
        "knockout_predictions": [
            {
                "bracket_slot": kp.bracket_slot,
                "stage": kp.stage.value,
                "sim_team_a_id": kp.sim_team_a_id,
                "sim_team_b_id": kp.sim_team_b_id,
                "predicted_score_a": kp.predicted_score_a,
                "predicted_score_b": kp.predicted_score_b,
            }
            for kp in ko_preds
        ],
        "special": {
            "top_scorer": sp.top_scorer if sp else None,
            "top_assister": sp.top_assister if sp else None,
            "submitted_at": sp.submitted_at.isoformat() if sp and sp.submitted_at else None,
        },
    }


@router.post("/submit")
async def submit_predictions(
    data: PredictionBulkSubmit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_locked(db)

    existing = await db.execute(select(Prediction).where(Prediction.user_id == user.id))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Predictions already submitted. Contact admin to reset.")

    match_ids = {p.match_id for p in data.predictions}
    match_result = await db.execute(select(Match).where(Match.id.in_(match_ids)))
    found = {m.id for m in match_result.scalars()}
    missing = match_ids - found
    if missing:
        raise HTTPException(status_code=400, detail=f"Invalid match IDs: {missing}")

    for p in data.predictions:
        db.add(
            Prediction(
                user_id=user.id,
                match_id=p.match_id,
                predicted_score_a=p.predicted_score_a,
                predicted_score_b=p.predicted_score_b,
            )
        )

    for kp in data.knockout_predictions:
        db.add(
            KnockoutPrediction(
                user_id=user.id,
                bracket_slot=kp.bracket_slot,
                stage=MatchStage(kp.stage),
                sim_team_a_id=kp.sim_team_a_id,
                sim_team_b_id=kp.sim_team_b_id,
                predicted_score_a=kp.predicted_score_a,
                predicted_score_b=kp.predicted_score_b,
            )
        )

    if data.top_scorer or data.top_assister:
        db.add(
            SpecialPrediction(
                user_id=user.id,
                top_scorer=data.top_scorer,
                top_assister=data.top_assister,
                submitted_at=datetime.now(timezone.utc),
            )
        )

    await db.flush()
    return {
        "message": "Predictions submitted successfully",
        "count": len(data.predictions),
        "knockout_count": len(data.knockout_predictions),
    }


@router.get("/status")
async def prediction_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Prediction).where(Prediction.user_id == user.id))
    count = len(result.scalars().all())
    settings_result = await db.execute(select(TournamentSettings).limit(1))
    settings = settings_result.scalar_one_or_none()
    return {
        "submitted": count > 0,
        "prediction_count": count,
        "locked": settings.predictions_locked if settings else False,
    }
