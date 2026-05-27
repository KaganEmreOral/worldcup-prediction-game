from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import KnockoutPrediction, Match, MatchStage, Prediction, Team, User
from app.services.group_simulation import MatchResult, compute_group_standings, rank_third_place_teams
from app.services.knockout_generator import build_knockout_tree, generate_r32_bracket
from app.services.scoring_engine import simulate_user_groups
from app.services.tournament_config import get_knockout_rules
from app.seeds.tournament_loader import get_active_tournament

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


class GroupPredictionPreview(BaseModel):
    match_id: int
    predicted_score_a: int = Field(ge=0)
    predicted_score_b: int = Field(ge=0)


class BracketPreviewRequest(BaseModel):
    predictions: list[GroupPredictionPreview]


async def _teams_by_group(db: AsyncSession) -> dict[str, list]:
    tournament = await get_active_tournament(db)
    q = select(Team).order_by(Team.group_name, Team.name)
    if tournament:
        q = q.where(Team.tournament_id == tournament.id)
    teams = (await db.execute(q)).scalars().all()
    by_group: dict[str, list] = {}
    for t in teams:
        if t.group_name:
            by_group.setdefault(t.group_name, []).append((t.id, t.name, t.code))
    return by_group


@router.post("/preview-bracket")
async def preview_bracket_from_predictions(
    data: BracketPreviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview knockout bracket from in-progress group predictions (before submit)."""
    teams_by_group = await _teams_by_group(db)
    tournament = await get_active_tournament(db)
    q = select(Match).where(Match.stage == MatchStage.GROUP)
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    group_matches = (await db.execute(q)).scalars().all()
    predictions = {p.match_id: (p.predicted_score_a, p.predicted_score_b) for p in data.predictions}
    if not predictions:
        return {"r32": [], "bracket": {}}
    rules = await get_knockout_rules(db)
    user_qualifiers = simulate_user_groups(teams_by_group, predictions, group_matches)
    all_standings = {}
    for group_name, team_list in teams_by_group.items():
        results = []
        for m in group_matches:
            if m.group_name == group_name and m.id in predictions:
                sa, sb = predictions[m.id]
                results.append(MatchResult(m.team_a_id, m.team_b_id, sa, sb))
        if results:
            all_standings[group_name] = compute_group_standings(team_list, results)
    third_ranked = rank_third_place_teams(all_standings)
    r32 = generate_r32_bracket(user_qualifiers, third_ranked, rules)
    tree = build_knockout_tree(r32, rules)
    return {"qualifiers": user_qualifiers, "r32": tree.get("R32", []), "bracket": tree}


@router.get("/my-bracket")
async def get_my_bracket(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return user's simulated knockout bracket based on their predictions."""
    teams_by_group = await _teams_by_group(db)
    tournament = await get_active_tournament(db)

    q = select(Match).where(Match.stage == MatchStage.GROUP)
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    group_matches = (await db.execute(q)).scalars().all()

    pred_result = await db.execute(select(Prediction).where(Prediction.user_id == user.id))
    predictions = {p.match_id: (p.predicted_score_a, p.predicted_score_b) for p in pred_result.scalars()}

    if not predictions:
        return {"message": "No predictions yet", "qualifiers": {}, "bracket": {}}

    rules = await get_knockout_rules(db)
    user_qualifiers = simulate_user_groups(teams_by_group, predictions, group_matches)

    all_standings = {}
    for group_name, team_list in teams_by_group.items():
        results = []
        for m in group_matches:
            if m.group_name == group_name and m.id in predictions:
                sa, sb = predictions[m.id]
                results.append(MatchResult(m.team_a_id, m.team_b_id, sa, sb))
        if results:
            all_standings[group_name] = compute_group_standings(team_list, results)

    third_ranked = rank_third_place_teams(all_standings)
    r32 = generate_r32_bracket(user_qualifiers, third_ranked, rules)

    ko_result = await db.execute(select(KnockoutPrediction).where(KnockoutPrediction.user_id == user.id))
    ko_preds = {kp.bracket_slot: (kp.predicted_score_a, kp.predicted_score_b) for kp in ko_result.scalars()}

    r16_preds = {k: v for k, v in ko_preds.items() if k.startswith("R16")}
    qf_preds = {k: v for k, v in ko_preds.items() if k.startswith("QF")}
    sf_preds = {k: v for k, v in ko_preds.items() if k.startswith("SF")}
    final_preds = {k: v for k, v in ko_preds.items() if k.startswith("F")}

    tree = build_knockout_tree(r32, rules, r16_preds, qf_preds, sf_preds, final_preds)

    for stage_matches in tree.values():
        for m in stage_matches:
            slot = m["label"]
            if slot in ko_preds:
                sa, sb = ko_preds[slot]
                m["prediction"] = {"score_a": sa, "score_b": sb}

    return {"qualifiers": user_qualifiers, "r32": tree.get("R32", []), "bracket": tree}
