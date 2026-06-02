"""Universe A vs B: scoring uses round participant sets, not bracket path."""

from app.services.knockout_scoring import score_knockout_round_participation


def test_same_team_different_path_still_scores():
    """Brazil in user QF and real QF — points even if R32 paths differ."""
    user_tree = {
        "R32": [
            {"team_a": {"id": 10}, "team_b": {"id": 20}},
            {"team_a": {"id": 1}, "team_b": {"id": 99}},
        ],
        "QF": [
            {"team_a": {"id": 1}, "team_b": {"id": 2}},
            {"team_a": {"id": 3}, "team_b": {"id": 4}},
        ],
        "F": [{"team_a": {"id": 1}, "team_b": {"id": 5}, "winner_id": 1}],
    }
    real_tree = {
        "R32": [
            {"team_a": {"id": 1}, "team_b": {"id": 88}},
            {"team_a": {"id": 77}, "team_b": {"id": 66}},
        ],
        "QF": [
            {"team_a": {"id": 1}, "team_b": {"id": 6}},
            {"team_a": {"id": 7}, "team_b": {"id": 8}},
        ],
        "F": [{"team_a": {"id": 1}, "team_b": {"id": 9}, "winner_id": 1}],
    }
    pts, details = score_knockout_round_participation(user_tree, real_tree)
    # Team 1 in QF (8) + F (15) + champion (40)
    assert pts >= 8 + 15 + 40
    assert any(d.get("type") == "champion" for d in details)


def test_r32_participation_scored():
    user_tree = {
        "R32": [{"team_a": {"id": 1}, "team_b": {"id": 2}}, {"team_a": {"id": 3}, "team_b": {"id": 4}}],
    }
    real_tree = {
        "R32": [{"team_a": {"id": 1}, "team_b": {"id": 99}}, {"team_a": {"id": 3}, "team_b": {"id": 88}}],
    }
    pts, _ = score_knockout_round_participation(user_tree, real_tree)
    assert pts == 8  # teams 1 and 3 at R32: 2 × 4
