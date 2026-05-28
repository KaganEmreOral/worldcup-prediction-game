"""Result-driven scoring: admin match results trigger automatic leaderboard updates."""

import os
import uuid

import httpx
import pytest

from app.models import Match, MatchStage, MatchStatus
from app.services.match_scoring import is_scorable_result
from app.services.scoring_engine import score_group_match

API_BASE = os.environ.get("TEST_API_BASE", "http://127.0.0.1:8000/api")


@pytest.fixture
def api():
    with httpx.Client(base_url=API_BASE, timeout=60.0) as client:
        yield client


def test_group_scoring_outcome_vs_exact():
    exact_pts, _ = score_group_match(2, 1, 2, 1)
    assert exact_pts == 8
    outcome_pts, _ = score_group_match(2, 0, 1, 0)
    assert outcome_pts == 3
    wrong_pts, _ = score_group_match(0, 2, 2, 1)
    assert wrong_pts == 0


def test_is_scorable_result_requires_finished():
    m = Match(
        id=1,
        stage=MatchStage.GROUP,
        team_a_id=1,
        team_b_id=2,
        real_score_a=1,
        real_score_b=0,
        status=MatchStatus.SCHEDULED,
    )
    assert not is_scorable_result(m)
    m.status = MatchStatus.FINISHED
    assert is_scorable_result(m)


def _admin_headers(api: httpx.Client) -> dict:
    res = api.post("/auth/login", json={"username": "admin", "password": "admin123"})
    if res.status_code != 200:
        pytest.skip(f"Admin login unavailable: {res.status_code}")
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_admin_match_save_triggers_scoring(api):
    try:
        headers = _admin_headers(api)
    except httpx.ConnectError:
        pytest.skip("API not reachable — start backend to run integration test")

    matches = api.get("/admin/matches?stage=group", headers=headers)
    assert matches.status_code == 200
    group = next((m for m in matches.json() if m.get("real_score_a") is None), None)
    if not group:
        pytest.skip("No group matches without results")

    patch = api.patch(
        f"/admin/matches/{group['id']}",
        headers=headers,
        json={"real_score_a": 1, "real_score_b": 0, "status": "finished"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json().get("scoring", {}).get("scored") is True
