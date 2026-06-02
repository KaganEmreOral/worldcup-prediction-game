from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import GroupStandingsCache, KnockoutPrediction, Prediction, User
from app.services.user_prediction_tournament import (
    build_user_prediction_tournament,
    load_user_prediction_tournament,
)
from app.services.tournament_config import get_knockout_rules
from app.seeds.tournament_loader import get_active_tournament
from app.services.prediction_validation import load_group_matches, load_teams_by_group

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


class GroupPredictionPreview(BaseModel):
    match_id: int
    predicted_score_a: int = Field(ge=0)
    predicted_score_b: int = Field(ge=0)


class BracketPreviewRequest(BaseModel):
    predictions: list[GroupPredictionPreview]
    knockout_predictions: list[dict] | None = None


def _attach_predictions(tree: dict, ko_preds: dict[str, tuple[int, int]]) -> None:
    for stage_matches in tree.values():
        for m in stage_matches:
            slot = m["label"]
            if slot in ko_preds:
                sa, sb = ko_preds[slot]
                m["prediction"] = {"score_a": sa, "score_b": sb}


@router.post("/preview-bracket")
async def preview_bracket_from_predictions(
    data: BracketPreviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview full per-user knockout bracket from group (and optional KO) predictions."""
    teams_by_group = await load_teams_by_group(db)
    group_matches = await load_group_matches(db)
    predictions = {p.match_id: (p.predicted_score_a, p.predicted_score_b) for p in data.predictions}
    if not predictions:
        return {"r32": [], "bracket": {}}

    ko_preds: dict[str, tuple[int, int]] = {}
    if data.knockout_predictions:
        for kp in data.knockout_predictions:
            slot = kp.get("bracket_slot")
            if slot:
                ko_preds[slot] = (kp.get("predicted_score_a", 0), kp.get("predicted_score_b", 0))

    rules = await get_knockout_rules(db)
    qualifiers, tree, _ = build_user_prediction_tournament(
        teams_by_group,
        group_matches,
        predictions,
        ko_preds,
        rules,
        allow_placeholder_winners=True,
    )
    _attach_predictions(tree, ko_preds)
    return {"qualifiers": qualifiers, "r32": tree.get("R32", []), "bracket": tree}


@router.get("/my-bracket")
async def get_my_bracket(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return user's simulated knockout bracket (cached after submit, or rebuilt live)."""
    cached = await load_user_prediction_tournament(db, user.id)
    if cached:
        standings_result = await db.execute(
            select(GroupStandingsCache).where(GroupStandingsCache.user_id == user.id)
        )
        qualifiers: dict[str, list] = {}
        for row in standings_result.scalars():
            qualifiers[row.group_name] = row.qualified_teams or []

        ko_result = await db.execute(
            select(KnockoutPrediction).where(KnockoutPrediction.user_id == user.id)
        )
        ko_preds = {
            kp.bracket_slot: (kp.predicted_score_a, kp.predicted_score_b)
            for kp in ko_result.scalars()
        }
        _attach_predictions(cached, ko_preds)
        return {"qualifiers": qualifiers, "r32": cached.get("R32", []), "bracket": cached, "cached": True}

    teams_by_group = await load_teams_by_group(db)
    group_matches = await load_group_matches(db)

    pred_result = await db.execute(select(Prediction).where(Prediction.user_id == user.id))
    predictions = {p.match_id: (p.predicted_score_a, p.predicted_score_b) for p in pred_result.scalars()}

    if not predictions:
        return {"message": "No predictions yet", "qualifiers": {}, "bracket": {}}

    ko_result = await db.execute(select(KnockoutPrediction).where(KnockoutPrediction.user_id == user.id))
    ko_preds = {kp.bracket_slot: (kp.predicted_score_a, kp.predicted_score_b) for kp in ko_result.scalars()}

    rules = await get_knockout_rules(db)
    qualifiers, tree, _ = build_user_prediction_tournament(
        teams_by_group,
        group_matches,
        predictions,
        ko_preds,
        rules,
        allow_placeholder_winners=not ko_preds,
    )
    _attach_predictions(tree, ko_preds)
    return {"qualifiers": qualifiers, "r32": tree.get("R32", []), "bracket": tree, "cached": False}
