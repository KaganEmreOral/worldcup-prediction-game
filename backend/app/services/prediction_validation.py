"""Validate complete tournament predictions before submission."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, MatchStage, Team
from app.schemas import PredictionBulkSubmit
from app.seeds.tournament_loader import get_active_tournament
from app.services.tournament_config import get_knockout_rules
from app.services.user_prediction_tournament import (
    build_user_prediction_tournament,
    validate_bracket_no_tbd,
)


async def load_group_matches(db: AsyncSession) -> list[Match]:
    tournament = await get_active_tournament(db)
    q = select(Match).where(Match.stage == MatchStage.GROUP).order_by(Match.match_number)
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    return list((await db.execute(q)).scalars().all())


async def load_knockout_matches(db: AsyncSession) -> list[Match]:
    tournament = await get_active_tournament(db)
    q = select(Match).where(Match.stage != MatchStage.GROUP).order_by(Match.match_number)
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    return list((await db.execute(q)).scalars().all())


async def load_teams_by_group(db: AsyncSession) -> dict[str, list[tuple[int, str, str]]]:
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


def _expected_knockout_labels(
    teams_by_group: dict,
    group_matches: list[Match],
    predictions: dict[int, tuple[int, int]],
    rules: dict,
) -> set[str]:
    """All knockout bracket_slot labels for this user's simulated groups."""
    _, tree, _ = build_user_prediction_tournament(
        teams_by_group,
        group_matches,
        predictions,
        {},
        rules,
        allow_placeholder_winners=True,
    )
    labels: set[str] = set()
    for stage_matches in tree.values():
        for m in stage_matches:
            labels.add(m["label"])
    return labels


async def validate_prediction_submission(db: AsyncSession, data: PredictionBulkSubmit) -> None:
    """Reject incomplete submissions (group, knockout, special, champion)."""
    errors: list[str] = []

    group_matches = await load_group_matches(db)
    expected_group_ids = {m.id for m in group_matches}
    submitted_ids = {p.match_id for p in data.predictions}

    if len(expected_group_ids) != 72:
        errors.append(f"Tournament has {len(expected_group_ids)} group matches (expected 72). Contact admin.")
    missing_group = sorted(expected_group_ids - submitted_ids)
    if missing_group:
        errors.append(f"Missing group predictions for {len(missing_group)} match(es).")
    extra_group = submitted_ids - expected_group_ids
    if extra_group:
        errors.append(f"Invalid group match IDs: {sorted(extra_group)[:5]}...")

    predictions_map = {p.match_id: (p.predicted_score_a, p.predicted_score_b) for p in data.predictions}

    if not (data.top_scorer and str(data.top_scorer).strip()):
        errors.append("Golden Boot (top scorer) is required.")
    if not (data.top_assister and str(data.top_assister).strip()):
        errors.append("Top assister is required.")

    rules = await get_knockout_rules(db)
    teams_by_group = await load_teams_by_group(db)
    expected_ko_labels = _expected_knockout_labels(
        teams_by_group, group_matches, predictions_map, rules
    )
    submitted_ko = {kp.bracket_slot for kp in data.knockout_predictions}
    missing_ko = sorted(expected_ko_labels - submitted_ko)
    if missing_ko:
        errors.append(f"Missing knockout predictions for {len(missing_ko)} match(es) (e.g. {missing_ko[:3]}).")

    for kp in data.knockout_predictions:
        if kp.predicted_score_a == kp.predicted_score_b:
            errors.append(f"Knockout match {kp.bracket_slot} must have a winner (no draws).")

    final_preds = [kp for kp in data.knockout_predictions if kp.stage == "F"]
    if not final_preds:
        errors.append("Final match prediction is required (champion).")

    if not errors and predictions_map:
        knockout_map = {
            kp.bracket_slot: (kp.predicted_score_a, kp.predicted_score_b)
            for kp in data.knockout_predictions
        }
        try:
            _, tree, _ = build_user_prediction_tournament(
                teams_by_group,
                group_matches,
                predictions_map,
                knockout_map,
                rules,
                allow_placeholder_winners=False,
            )
            validate_bracket_no_tbd(tree)
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        raise HTTPException(status_code=400, detail={"message": "Incomplete predictions", "errors": errors})
