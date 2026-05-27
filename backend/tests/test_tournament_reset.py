"""Admin reset must clear derived state and refresh leaderboard / dashboard projections."""

import os
import uuid

import httpx
import pytest

API_BASE = os.environ.get("TEST_API_BASE", "http://127.0.0.1:8000/api")


@pytest.fixture
def api():
    with httpx.Client(base_url=API_BASE, timeout=60.0) as client:
        yield client


def _admin_headers(api: httpx.Client) -> dict:
    res = api.post("/auth/login", json={"username": "admin", "password": "admin123"})
    if res.status_code != 200:
        pytest.skip(f"Admin login unavailable: {res.status_code}")
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_reset_match_results_zeros_leaderboard_and_dashboard(api):
    try:
        headers = _admin_headers(api)
    except httpx.ConnectError:
        pytest.skip("API not reachable")

    matches = api.get("/admin/matches", headers=headers)
    assert matches.status_code == 200
    group = next((m for m in matches.json() if m["stage"] == "group"), None)
    if not group:
        pytest.skip("No group matches")

    username = f"reset_{uuid.uuid4().hex[:8]}"
    reg = api.post("/auth/register", json={"username": username, "password": "password123"})
    assert reg.status_code == 201
    user_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    api.post(
        "/predictions/submit",
        headers=user_headers,
        json={
            "predictions": [{"match_id": group["id"], "predicted_score_a": 2, "predicted_score_b": 1}],
            "knockout_predictions": [],
        },
    )

    patch = api.patch(
        f"/admin/matches/{group['id']}",
        headers=headers,
        json={"real_score_a": 2, "real_score_b": 1, "status": "finished"},
    )
    assert patch.status_code == 200

    lb_before = api.get("/leaderboard")
    entry_before = next((e for e in lb_before.json() if e["username"] == username.lower()), None)
    assert entry_before and entry_before["total_score"] >= 8

    dash_before = api.get("/dashboard")
    assert dash_before.status_code == 200
    assert dash_before.json()["stats"]["finished_matches"] >= 1

    reset = api.post("/admin/reset-match-results", headers=headers)
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["matches_reset"] >= 1
    assert body["recompute"]["recomputed"] is True

    lb_after = api.get("/leaderboard")
    entry_after = next((e for e in lb_after.json() if e["username"] == username.lower()), None)
    assert entry_after is not None
    assert entry_after["total_score"] == 0

    dash_after = api.get("/dashboard")
    assert dash_after.json()["stats"]["finished_matches"] == 0
    assert dash_after.json()["latest_results"] == []

    # Scoring still works after reset
    patch2 = api.patch(
        f"/admin/matches/{group['id']}",
        headers=headers,
        json={"real_score_a": 1, "real_score_b": 0, "status": "finished"},
    )
    assert patch2.status_code == 200
    lb_final = api.get("/leaderboard")
    entry_final = next((e for e in lb_final.json() if e["username"] == username.lower()), None)
    assert entry_final and entry_final["total_score"] >= 3
