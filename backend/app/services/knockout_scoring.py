"""
Knockout scoring — compare user prediction tournament vs real tournament.

Scoring rule: SET OF TEAMS at each round (participation), never bracket position or matchup path.
"""

from __future__ import annotations

from app.services.bracket_participants import champion_team_id, teams_in_round

# Points per correctly predicted team in each round's participant pool
STAGE_PARTICIPATION_POINTS = {
    "R32": 4,
    "R16": 6,
    "QF": 8,
    "SF": 12,
    "F": 15,
}

CHAMPION_BONUS = 40


def score_knockout_round_participation(
    user_bracket_tree: dict,
    real_bracket_tree: dict,
) -> tuple[int, list]:
    """
    Compare team sets at each stage (R32 → F). Path/matchup ignored.

    Example: user predicted Brazil in QF; real tournament has Brazil in QF → points,
    even if they arrived via different R32/R16 paths.
    """
    from app.services.scoring_engine import _enrich_detail

    if not user_bracket_tree or not real_bracket_tree:
        return 0, []

    points = 0
    details: list = []

    for stage, pts_each in STAGE_PARTICIPATION_POINTS.items():
        user_teams = teams_in_round(user_bracket_tree, stage)
        real_teams = teams_in_round(real_bracket_tree, stage)
        if not real_teams:
            continue
        correct = user_teams & real_teams
        if correct:
            earned = len(correct) * pts_each
            points += earned
            details.append(
                _enrich_detail(
                    {
                        "type": "knockout_round_teams",
                        "stage": stage,
                        "teams": len(correct),
                        "team_ids": sorted(correct),
                        "points": earned,
                        "points_each": pts_each,
                    }
                )
            )

    real_champion = champion_team_id(real_bracket_tree)
    user_champion = champion_team_id(user_bracket_tree)
    if real_champion and user_champion and real_champion == user_champion:
        points += CHAMPION_BONUS
        details.append(_enrich_detail({"type": "champion", "points": CHAMPION_BONUS}))

    return points, details


# Backwards-compatible alias used by tests and legacy imports
def score_knockout_progression(user_tree: dict, real_tree: dict) -> tuple[int, list]:
    return score_knockout_round_participation(user_tree, real_tree)


def score_knockout_exact_bonuses(*_args, **_kwargs) -> tuple[int, list]:
    """Deprecated: matchup-based exact bonuses removed — scoring is round participation only."""
    return 0, []
