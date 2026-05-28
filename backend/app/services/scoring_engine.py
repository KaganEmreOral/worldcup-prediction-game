"""Scoring engine — evaluates predictions against real results."""

from dataclasses import dataclass, field

from app.models import MatchStage
from app.services.group_simulation import (
    MatchResult,
    compute_group_standings,
    get_qualified_teams,
)

DETAIL_LABELS = {
    "group_outcome": "Correct outcome (+3)",
    "group_exact": "Exact score (+5)",
    "qualification_team": "Correct qualifier (+4)",
    "group_winner": "Group winner (+5)",
    "full_group_bonus": "Perfect group (+10)",
    "knockout_advance": "Knockout progression",
    "finalist": "Correct finalist (+20)",
    "champion": "Champion correct (+40)",
    "knockout_exact": "Knockout exact score bonus",
    "top_scorer": "Golden Boot correct (+20)",
    "top_assister": "Top assister correct (+20)",
}


@dataclass
class ScoreBreakdown:
    group_match_points: int = 0
    qualification_points: int = 0
    group_winner_points: int = 0
    full_group_bonus: int = 0
    knockout_progression_points: int = 0
    knockout_exact_points: int = 0
    special_points: int = 0
    details: list = field(default_factory=list)
    match_scores: list = field(default_factory=list)

    @property
    def group_total(self) -> int:
        return self.group_match_points + self.qualification_points + self.group_winner_points + self.full_group_bonus

    @property
    def knockout_total(self) -> int:
        return self.knockout_progression_points + self.knockout_exact_points

    @property
    def total(self) -> float:
        return self.group_total + self.knockout_total + self.special_points


def _outcome(score_a: int, score_b: int) -> str:
    if score_a > score_b:
        return "win_a"
    if score_a < score_b:
        return "win_b"
    return "draw"


def _enrich_detail(detail: dict) -> dict:
    t = detail.get("type", "")
    if t == "knockout_advance":
        detail["label"] = (
            f"{detail.get('stage', 'KO')} advancement: {detail.get('teams', 0)} teams "
            f"(+{detail.get('points_each', 0)} each) = +{detail.get('points', 0)}"
        )
    elif t == "knockout_exact":
        detail["label"] = f"{detail.get('stage', 'KO')} exact score bonus (+{detail.get('points', 0)})"
    elif t in DETAIL_LABELS:
        detail["label"] = DETAIL_LABELS[t]
    else:
        detail["label"] = t.replace("_", " ").title()
    return detail


def score_group_match(pred_a: int, pred_b: int, real_a: int | None, real_b: int | None) -> tuple[int, list]:
    if real_a is None or real_b is None:
        return 0, []
    points = 0
    details = []
    outcome_ok = _outcome(pred_a, pred_b) == _outcome(real_a, real_b)
    exact = pred_a == real_a and pred_b == real_b
    if outcome_ok:
        points += 3
        details.append(_enrich_detail({"type": "group_outcome", "points": 3}))
    if exact:
        points += 5
        details.append(_enrich_detail({"type": "group_exact", "points": 5}))
    return points, details


def build_match_score_entry(
    match,
    pred_a: int,
    pred_b: int,
    real_a: int,
    real_b: int,
    points: int,
    details: list,
    *,
    bracket_slot: str | None = None,
) -> dict:
    outcome_ok = _outcome(pred_a, pred_b) == _outcome(real_a, real_b)
    exact = pred_a == real_a and pred_b == real_b
    status = "exact" if exact else "outcome" if outcome_ok else "wrong"
    return {
        "match_id": match.id,
        "match_number": getattr(match, "match_number", None),
        "bracket_slot": bracket_slot or getattr(match, "bracket_slot", None),
        "stage": match.stage.value if hasattr(match.stage, "value") else str(match.stage),
        "group_name": getattr(match, "group_name", None),
        "team_a_code": match.team_a.code if hasattr(match, "team_a") and match.team_a else None,
        "team_b_code": match.team_b.code if hasattr(match, "team_b") and match.team_b else None,
        "predicted": f"{pred_a}-{pred_b}",
        "actual": f"{real_a}-{real_b}",
        "points": points,
        "reasons": [_enrich_detail(d) for d in details],
        "status": status,
        "outcome_correct": outcome_ok,
        "exact": exact,
    }


def score_qualification(
    predicted_qualifiers: dict[str, list[dict]],
    real_qualifiers: dict[str, list[dict]],
) -> tuple[int, int, int, list]:
    qual_points = 0
    winner_points = 0
    full_bonus = 0
    details = []

    real_qualified_ids = set()
    real_winners: dict[str, int] = {}
    for group, teams in real_qualifiers.items():
        for t in teams:
            real_qualified_ids.add(t["team_id"])
        if teams:
            real_winners[group] = teams[0]["team_id"]

    pred_qualified_ids = set()
    pred_winners: dict[str, int] = {}
    for group, teams in predicted_qualifiers.items():
        for t in teams:
            pred_qualified_ids.add(t["team_id"])
        if teams:
            pred_winners[group] = teams[0]["team_id"]

    for tid in pred_qualified_ids & real_qualified_ids:
        qual_points += 4
        details.append(_enrich_detail({"type": "qualification_team", "team_id": tid, "points": 4}))

    for group, winner_id in pred_winners.items():
        if real_winners.get(group) == winner_id:
            winner_points += 5
            details.append(_enrich_detail({"type": "group_winner", "group": group, "points": 5}))

    for group in predicted_qualifiers:
        pred_set = {t["team_id"] for t in predicted_qualifiers.get(group, [])}
        real_set = {t["team_id"] for t in real_qualifiers.get(group, [])}
        if pred_set == real_set and pred_set:
            full_bonus += 10
            details.append(_enrich_detail({"type": "full_group_bonus", "group": group, "points": 10}))

    return qual_points, winner_points, full_bonus, details


def simulate_user_groups(
    teams_by_group: dict[str, list[tuple[int, str, str]]],
    group_predictions: dict[int, tuple[int, int]],
    matches: list,
) -> dict[str, list]:
    if not group_predictions:
        return {}
    all_standings = {}
    for group_name, team_list in teams_by_group.items():
        results = []
        for m in matches:
            if m.group_name != group_name:
                continue
            if m.id in group_predictions:
                sa, sb = group_predictions[m.id]
                results.append(MatchResult(m.team_a_id, m.team_b_id, sa, sb))
        if results:
            all_standings[group_name] = compute_group_standings(team_list, results)
    if len(all_standings) < len(teams_by_group):
        return {}
    return get_qualified_teams(all_standings)


def simulate_real_groups(
    teams_by_group: dict[str, list[tuple[int, str, str]]],
    matches: list,
) -> dict[str, list]:
    all_standings = {}
    for group_name, team_list in teams_by_group.items():
        results = []
        for m in matches:
            if m.group_name != group_name:
                continue
            if m.real_score_a is not None and m.real_score_b is not None:
                results.append(MatchResult(m.team_a_id, m.team_b_id, m.real_score_a, m.real_score_b))
        if results:
            all_standings[group_name] = compute_group_standings(team_list, results)
    if not all_standings:
        return {}
    return get_qualified_teams(all_standings)
