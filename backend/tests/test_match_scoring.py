"""Result-driven scoring: admin match results trigger automatic leaderboard updates."""

import os
import uuid

import httpx
import pytest

from app.models import Match, MatchStage, MatchStatus
from app.services.match_scoring import is_scorable_result
from app.services.scoring_engine import score_group_match, score_knockout_match

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


def test_knockout_scoring_final():
    winner_pts, exact_pts, _ = score_knockout_match(MatchStage.F, 2, 1, 2, 1)
    assert winner_pts == 30 and exact_pts == 15


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

    matches = api.get("/admin/matches", headers=headers)
    assert matches.status_code == 200
    group = next(
        (m for m in matches.json() if m["stage"] == "group" and m.get("real_score_a") is None),
        None,
    )
    if not group:
        group = next((m for m in matches.json() if m["stage"] == "group"), None)
    if not group:
        pytest.skip("No group matches in database")

    username = f"scorer_{uuid.uuid4().hex[:8]}"
    reg = api.post("/auth/register", json={"username": username, "password": "password123"})
    assert reg.status_code == 201, reg.text
    user_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    submit = api.post(
        "/predictions/submit",
        headers=user_headers,
        json={
            "predictions": [
                {
                    "match_id": group["id"],
                    "predicted_score_a": 2,
                    "predicted_score_b": 1,
                }
            ],
            "knockout_predictions": [],
        },
    )
    assert submit.status_code == 200, submit.text

    patch = api.patch(
        f"/admin/matches/{group['id']}",
        headers=headers,
        json={"real_score_a": 2, "real_score_b": 1, "status": "finished"},
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body.get("scoring", {}).get("scored") is True
    assert body["scoring"]["users_scored"] >= 1

    lb = api.get("/leaderboard")
    assert lb.status_code == 200
    entry = next((e for e in lb.json() if e["username"] == username.lower()), None)
    assert entry is not None
    assert entry["total_score"] >= 8

    patch2 = api.patch(
        f"/admin/matches/{group['id']}",
        headers=headers,
        json={"real_score_a": 0, "real_score_b": 0, "status": "finished"},
    )
    assert patch2.status_code == 200
    lb2 = api.get("/leaderboard")
    entry2 = next((e for e in lb2.json() if e["username"] == username.lower()), None)
    assert entry2 is not None
    assert entry2["total_score"] < entry["total_score"]
