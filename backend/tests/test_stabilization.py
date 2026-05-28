"""Stabilization: match counts, submission validation, scoring rules."""

import json
from pathlib import Path

import pytest

from app.schemas import KnockoutPredictionCreate, PredictionBulkSubmit, PredictionCreate
from app.services.prediction_validation import _expected_knockout_labels
from app.services.scoring_engine import score_group_match, score_qualification
from app.services.knockout_scoring import score_knockout_progression
from app.seeds.tournament_loader import load_seed_bundle, validate_seed_bundle

SEEDS = Path(__file__).resolve().parent.parent / "app" / "seeds" / "tournaments" / "worldcup_2026"


@pytest.mark.asyncio
async def test_seed_has_72_group_matches():
    bundle = load_seed_bundle("worldcup_2026")
    errors = await validate_seed_bundle(bundle)
    assert not errors, errors
    assert len(bundle["matches"]["group_matches"]) == 72


def test_group_match_scoring_outcome_and_exact():
    exact, _ = score_group_match(2, 1, 2, 1)
    assert exact == 8
    outcome_only, _ = score_group_match(2, 0, 1, 0)
    assert outcome_only == 3
    wrong, _ = score_group_match(1, 1, 2, 1)
    assert wrong == 0


def test_qualification_points_per_team():
    pred = {
        "A": [{"team_id": 1, "position": 1}, {"team_id": 2, "position": 2}],
        "B": [{"team_id": 3, "position": 1}, {"team_id": 4, "position": 2}],
    }
    real = {
        "A": [{"team_id": 1, "position": 1}, {"team_id": 2, "position": 2}],
        "B": [{"team_id": 3, "position": 1}, {"team_id": 99, "position": 2}],
    }
    qp, wp, fb, _ = score_qualification(pred, real)
    assert qp == 4 * 3  # teams 1,2,3 correct
    assert wp == 5 * 2  # both group winners
    assert fb == 10  # group A perfect


def test_knockout_progression_champion():
    user_tree = {
        "R16": [{"team_a": {"id": 1}, "team_b": {"id": 2}}],
        "F": [{"team_a": {"id": 1}, "team_b": {"id": 3}, "winner_id": 1}],
    }
    real_tree = {
        "R16": [{"team_a": {"id": 1}, "team_b": {"id": 99}}],
        "F": [{"team_a": {"id": 1}, "team_b": {"id": 3}, "winner_id": 1}],
    }
    pts, _ = score_knockout_progression(user_tree, real_tree)
    assert pts >= 40 + 20  # champion + at least one finalist


def test_incomplete_submission_schema():
    data = PredictionBulkSubmit(
        predictions=[PredictionCreate(match_id=1, predicted_score_a=1, predicted_score_b=0)],
        knockout_predictions=[],
        top_scorer=None,
        top_assister=None,
    )
    assert len(data.predictions) == 1
    assert not data.top_scorer
