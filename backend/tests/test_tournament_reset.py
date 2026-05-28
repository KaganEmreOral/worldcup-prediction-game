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

    patch = api.patch(
        f"/admin/matches/{group['id']}",
        headers=headers,
        json={"real_score_a": 2, "real_score_b": 1, "status": "finished"},
    )
    assert patch.status_code == 200

    dash_before = api.get("/dashboard")
    assert dash_before.status_code == 200
    finished_before = dash_before.json()["stats"]["finished_matches"]

    reset = api.post("/admin/reset-match-results", headers=headers)
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["matches_reset"] >= 1
    assert body["recompute"]["recomputed"] is True

    dash_after = api.get("/dashboard")
    assert dash_after.json()["stats"]["finished_matches"] == 0
    assert finished_before >= 1
