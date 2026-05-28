"""Knockout progression and matchup scoring vs real admin-entered bracket."""

from __future__ import annotations

from app.models import Match, MatchStage
from app.services.knockout_generator import BracketMatch, BracketTeam, build_knockout_tree, generate_r32_bracket
from app.services.group_simulation import rank_third_place_teams
from app.services.scoring_engine import _enrich_detail, simulate_real_groups, simulate_user_groups

STAGE_ADVANCE_POINTS = {
    "R16": ("R32", 6),
    "QF": ("R16", 8),
    "SF": ("QF", 12),
    "F": ("SF", 15),
}

STAGE_EXACT_BONUS = {
    MatchStage.R32: 4,
    MatchStage.R16: 5,
    MatchStage.QF: 6,
    MatchStage.SF: 8,
    MatchStage.F: 15,
}


def _teams_in_round(tree: dict, stage: str) -> set[int]:
    ids: set[int] = set()
    for m in tree.get(stage, []):
        if m.get("team_a"):
            ids.add(m["team_a"]["id"])
        if m.get("team_b"):
            ids.add(m["team_b"]["id"])
    return ids


def _final_winner_id(tree: dict) -> int | None:
    finals = tree.get("F", [])
    if not finals:
        return None
    f = finals[0]
    return f.get("winner_id")


def _preds_by_stage(knockout_preds: dict[str, tuple[int, int]]) -> tuple[dict, dict, dict, dict, dict]:
    """Split bracket_slot predictions into per-stage dicts for build_knockout_tree."""
    r32, r16, qf, sf, final = {}, {}, {}, {}, {}
    for slot, scores in knockout_preds.items():
        if slot.startswith("R32"):
            r32[slot] = scores
        elif slot.startswith("R16"):
            r16[slot] = scores
        elif slot.startswith("QF"):
            qf[slot] = scores
        elif slot.startswith("SF"):
            sf[slot] = scores
        elif slot.startswith("F"):
            final[slot] = scores
    return r32, r16, qf, sf, final


def build_user_knockout_tree(
    teams_by_group: dict,
    group_predictions: dict[int, tuple[int, int]],
    group_matches: list,
    knockout_preds: dict[str, tuple[int, int]],
    rules: dict,
) -> dict:
    user_qualifiers = simulate_user_groups(teams_by_group, group_predictions, group_matches)
    if not user_qualifiers:
        return {}
    from app.services.group_simulation import MatchResult, compute_group_standings

    all_standings = {}
    for group_name, team_list in teams_by_group.items():
        results = []
        for m in group_matches:
            if m.group_name == group_name and m.id in group_predictions:
                sa, sb = group_predictions[m.id]
                results.append(MatchResult(m.team_a_id, m.team_b_id, sa, sb))
        if results:
            all_standings[group_name] = compute_group_standings(team_list, results)
    third_ranked = rank_third_place_teams(all_standings)
    r32 = generate_r32_bracket(user_qualifiers, third_ranked, rules)
    r32p, r16, qf, sf, final = _preds_by_stage(knockout_preds)
    return build_knockout_tree(r32, rules, r32_preds=r32p, r16_preds=r16, qf_preds=qf, sf_preds=sf, final_pred=final)


def build_real_knockout_tree(
    teams_by_group: dict,
    group_matches: list,
    knockout_preds: dict[str, tuple[int, int]],
    rules: dict,
) -> dict:
    real_qualifiers = simulate_real_groups(teams_by_group, group_matches)
    if not real_qualifiers:
        return {}
    all_standings = {}
    from app.services.group_simulation import MatchResult, compute_group_standings

    for group_name, team_list in teams_by_group.items():
        results = []
        for m in group_matches:
            if m.group_name == group_name and m.real_score_a is not None and m.real_score_b is not None:
                results.append(MatchResult(m.team_a_id, m.team_b_id, m.real_score_a, m.real_score_b))
        if results:
            all_standings[group_name] = compute_group_standings(team_list, results)
    third_ranked = rank_third_place_teams(all_standings)
    r32 = generate_r32_bracket(real_qualifiers, third_ranked, rules)
    r32p, r16, qf, sf, final = _preds_by_stage(knockout_preds)
    return build_knockout_tree(r32, rules, r32_preds=r32p, r16_preds=r16, qf_preds=qf, sf_preds=sf, final_pred=final)


def real_knockout_preds_from_matches(knockout_matches: list[Match]) -> dict[str, tuple[int, int]]:
    preds = {}
    for m in knockout_matches:
        if m.bracket_slot and m.real_score_a is not None and m.real_score_b is not None:
            preds[m.bracket_slot] = (m.real_score_a, m.real_score_b)
    return preds


def score_knockout_progression(user_tree: dict, real_tree: dict) -> tuple[int, list]:
    if not user_tree or not real_tree:
        return 0, []
    points = 0
    details = []
    for next_stage, (_prev, pts_per) in STAGE_ADVANCE_POINTS.items():
        user_teams = _teams_in_round(user_tree, next_stage)
        real_teams = _teams_in_round(real_tree, next_stage)
        correct = user_teams & real_teams
        if correct:
            earned = len(correct) * pts_per
            points += earned
            details.append(
                _enrich_detail(
                    {
                        "type": "knockout_advance",
                        "stage": next_stage,
                        "teams": len(correct),
                        "points": earned,
                        "points_each": pts_per,
                    }
                )
            )

    real_finalists = _teams_in_round(real_tree, "F")
    user_finalists = _teams_in_round(user_tree, "F")
    finalist_hits = user_finalists & real_finalists
    if finalist_hits:
        earned = len(finalist_hits) * 20
        points += earned
        details.append(_enrich_detail({"type": "finalist", "teams": len(finalist_hits), "points": earned}))

    real_champion = _final_winner_id(real_tree)
    user_champion = _final_winner_id(user_tree)
    if real_champion and user_champion and real_champion == user_champion:
        points += 40
        details.append(_enrich_detail({"type": "champion", "points": 40}))

    return points, details


def score_knockout_exact_bonuses(
    user_ko_preds: dict,
    knockout_matches: list[Match],
) -> tuple[int, list]:
    """Exact score bonus when real matchup exists and user predicted same teams + score."""
    points = 0
    details = []
    real_by_slot = {m.bracket_slot: m for m in knockout_matches if m.bracket_slot}

    for slot, m in real_by_slot.items():
        if m.real_score_a is None or m.real_score_b is None:
            continue
        kp = user_ko_preds.get(slot)
        if not kp:
            continue
        pred_a, pred_b = kp.predicted_score_a, kp.predicted_score_b
        if pred_a == pred_b:
            continue
        pred_winner_a = pred_a > pred_b
        real_winner_a = m.real_score_a > m.real_score_b
        if pred_winner_a != real_winner_a:
            continue
        pred_teams = {kp.sim_team_a_id, kp.sim_team_b_id} - {None}
        real_teams = {m.team_a_id, m.team_b_id}
        if pred_teams != real_teams:
            continue
        if pred_a != m.real_score_a or pred_b != m.real_score_b:
            continue
        bonus = STAGE_EXACT_BONUS.get(m.stage, 0)
        if bonus:
            points += bonus
            details.append(
                _enrich_detail(
                    {"type": "knockout_exact", "stage": m.stage.value, "bracket_slot": slot, "points": bonus}
                )
            )
    return points, details
