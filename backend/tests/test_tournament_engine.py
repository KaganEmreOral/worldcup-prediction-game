"""Validation tests for tournament engine."""

import json
from pathlib import Path

import pytest

from app.services.group_simulation import (
    MatchResult,
    compute_group_standings,
    get_qualified_teams,
    rank_third_place_teams,
)
from app.services.knockout_generator import assign_third_place_teams, generate_r32_bracket, load_rules_from_dict
from app.services.scoring_engine import score_group_match, score_knockout_match, score_qualification
from app.models import MatchStage

SEEDS = Path(__file__).resolve().parent.parent / "app" / "seeds" / "tournaments" / "worldcup_2026"


@pytest.fixture
def rules():
    data = json.loads((SEEDS / "knockout_rules.json").read_text())
    data["third_place_scenarios"] = json.loads((SEEDS / "third_place_scenarios.json").read_text())
    return load_rules_from_dict(data)


def _make_group(team_ids: list[tuple[int, str, str]], results: list[tuple[int, int, int, int]]):
    """results: (team_a_idx, team_b_idx, score_a, score_b) using indices into team_ids."""
    match_results = [
        MatchResult(team_ids[a][0], team_ids[b][0], sa, sb) for a, b, sa, sb in results
    ]
    return compute_group_standings(team_ids, match_results)


def test_standings_ranking_by_points():
    teams = [(1, "A", "AAA"), (2, "B", "BBB"), (3, "C", "CCC"), (4, "D", "DDD")]
    # A beats everyone
    standings = _make_group(teams, [(0, 1, 2, 0), (0, 2, 1, 0), (0, 3, 3, 0), (1, 2, 1, 1), (1, 3, 2, 1), (2, 3, 0, 0)])
    assert standings[0].team_id == 1
    assert standings[0].points == 9


def test_best_third_qualification():
    all_standings = {}
    for i, letter in enumerate("ABCD"):
        base = i * 4
        teams = [(base + 1, f"T{base+1}", f"T{base+1}"), (base + 2, f"T{base+2}", f"T{base+2}"),
                 (base + 3, f"T{base+3}", f"T{base+3}"), (base + 4, f"T{base+4}", f"T{base+4}")]
        results = [
            MatchResult(base + 1, base + 2, 1, 0),
            MatchResult(base + 1, base + 3, 1, 0),
            MatchResult(base + 1, base + 4, 1, 0),
            MatchResult(base + 2, base + 3, 1, 0),
            MatchResult(base + 2, base + 4, 1, 0),
            MatchResult(base + 3, base + 4, 3, 0),
        ]
        all_standings[letter] = compute_group_standings(teams, results)

    third = rank_third_place_teams(all_standings)
    assert len(third) == 4
    qualifiers = get_qualified_teams(all_standings, num_best_third=2)
    third_qualified = sum(1 for g in qualifiers.values() for t in g if t.get("qualification") == "best_third")
    assert third_qualified == 2


def test_third_place_scenario_lookup(rules):
    from app.services.knockout_generator import _build_scenario_lookup

    lookup = _build_scenario_lookup(rules)
    assert len(lookup) == 495
    key = tuple(sorted(["E", "F", "G", "H", "I", "J", "K", "L"]))
    assert key in lookup
    assert lookup[key]["74"] == "F"


def test_r32_bracket_generation(rules):
    qualifiers = {
        "A": [{"team_id": 1, "team_name": "Mexico", "team_code": "MEX", "position": 1},
              {"team_id": 2, "team_name": "Korea", "team_code": "KOR", "position": 2}],
        "B": [{"team_id": 3, "team_name": "Canada", "team_code": "CAN", "position": 1},
              {"team_id": 4, "team_name": "SUI", "team_code": "SUI", "position": 2}],
    }
    for letter in "CDEFGHIJKL":
        if letter not in qualifiers:
            qualifiers[letter] = [
                {"team_id": 10, "team_name": f"W{letter}", "team_code": f"W{letter}", "position": 1},
                {"team_id": 11, "team_name": f"R{letter}", "team_code": f"R{letter}", "position": 2},
                {"team_id": 12, "team_name": f"T{letter}", "team_code": f"T{letter}", "position": 3, "qualification": "best_third"},
            ]

    from app.services.group_simulation import ThirdPlaceCandidate

    third_ranked = [
        ThirdPlaceCandidate(12, f"T{g}", f"T{g}", g, 3, 0, 1, 3)
        for g in ["E", "F", "G", "H", "I", "J", "K", "L"]
    ]
    r32 = generate_r32_bracket(qualifiers, third_ranked, rules)
    assert len(r32) == 16
    m73 = next(m for m in r32 if m.match_number == 73)
    assert m73.team_a and m73.team_b


def test_score_group_match():
    pts, _ = score_group_match(2, 1, 2, 1)
    assert pts == 8  # outcome + exact
    pts2, _ = score_group_match(2, 0, 1, 0)
    assert pts2 == 3  # outcome only


def test_score_knockout_match():
    wp, ep, _ = score_knockout_match(MatchStage.F, 2, 1, 2, 1)
    assert wp == 30 and ep == 15


def test_score_qualification():
    pred = {"A": [{"team_id": 1, "position": 1}, {"team_id": 2, "position": 2}]}
    real = {"A": [{"team_id": 1, "position": 1}, {"team_id": 3, "position": 2}]}
    qp, wp, fb, _ = score_qualification(pred, real)
    assert qp == 5  # team 1 qualified in both
    assert wp == 3  # group winner correct
