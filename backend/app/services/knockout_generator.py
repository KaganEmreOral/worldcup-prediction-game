"""Knockout bracket generator — configurable FIFA-style rules from tournament data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "seeds" / "tournaments" / "worldcup_2026"


@dataclass
class BracketTeam:
    team_id: int
    team_name: str
    team_code: str
    source: str


@dataclass
class BracketMatch:
    label: str
    match_number: int | None
    team_a: BracketTeam | None
    team_b: BracketTeam | None
    winner: BracketTeam | None = None
    score_a: int | None = None
    score_b: int | None = None


def load_rules_from_dict(rules: dict) -> dict:
    return rules


@lru_cache(maxsize=4)
def _load_default_scenarios() -> dict[tuple[str, ...], dict[str, str]]:
    path = DEFAULT_RULES_PATH / "third_place_scenarios.json"
    if not path.exists():
        return {}
    scenarios = json.loads(path.read_text())
    lookup: dict[tuple[str, ...], dict[str, str]] = {}
    for s in scenarios:
        key = tuple(sorted(s["qualifying_groups"]))
        lookup[key] = s["assignments"]
    return lookup


def _build_scenario_lookup(rules: dict) -> dict[tuple[str, ...], dict[str, str]]:
    scenarios = rules.get("third_place_scenarios")
    if not scenarios:
        return _load_default_scenarios()
    lookup: dict[tuple[str, ...], dict[str, str]] = {}
    for s in scenarios:
        key = tuple(sorted(s["qualifying_groups"]))
        lookup[key] = {str(k): v for k, v in s["assignments"].items()}
    return lookup


def _resolve_group_position(
    group_name: str,
    position: int,
    group_qualifiers: dict[str, list[dict]],
) -> BracketTeam | None:
    for t in group_qualifiers.get(group_name, []):
        if t.get("position") == position:
            return BracketTeam(
                team_id=t["team_id"],
                team_name=t["team_name"],
                team_code=t["team_code"],
                source=f"{group_name}{position}",
            )
    return None


def _resolve_team_slot(
    slot: str,
    group_qualifiers: dict[str, list[dict]],
    third_assignments: dict[int, BracketTeam],
) -> BracketTeam | None:
    if slot == "3RD":
        return None
    if len(slot) >= 2 and slot[0].isalpha() and slot[1].isdigit():
        group = slot[0]
        pos = int(slot[1])
        return _resolve_group_position(group, pos, group_qualifiers)
    return None


def assign_third_place_teams(
    third_ranked: list,
    rules: dict,
) -> dict[int, BracketTeam]:
    """Assign third-placed teams to R32 slots using FIFA Annex C scenario lookup."""
    qualifying_groups = tuple(sorted(c.group_name for c in third_ranked))
    lookup = _build_scenario_lookup(rules)
    scenario = lookup.get(qualifying_groups)
    if not scenario:
        return {}

    third_by_group = {c.group_name: c for c in third_ranked}
    assignments: dict[int, BracketTeam] = {}
    for match_num_str, group_letter in scenario.items():
        match_num = int(match_num_str)
        candidate = third_by_group.get(group_letter)
        if candidate:
            assignments[match_num] = BracketTeam(
                team_id=candidate.team_id,
                team_name=candidate.team_name,
                team_code=candidate.team_code,
                source=f"3rd-{candidate.group_name}",
            )
    return assignments


def generate_r32_bracket(
    group_qualifiers: dict[str, list[dict]],
    third_ranked: list,
    rules: dict | None = None,
) -> list[BracketMatch]:
    rules = rules or {}
    third_assignments = assign_third_place_teams(third_ranked, rules)
    r32_template = rules.get("r32_fixed", [])

    matches: list[BracketMatch] = []
    for entry in r32_template:
        slot_a = entry["team_a"]
        slot_b = entry["team_b"]
        match_num = entry["match_number"]

        team_a = _resolve_team_slot(slot_a, group_qualifiers, third_assignments)
        if slot_b == "3RD":
            team_b = third_assignments.get(entry.get("third_slot_match", match_num))
        else:
            team_b = _resolve_team_slot(slot_b, group_qualifiers, third_assignments)

        matches.append(
            BracketMatch(
                label=entry["bracket_slot"],
                match_number=match_num,
                team_a=team_a,
                team_b=team_b,
            )
        )
    return matches


def advance_knockout_round(
    matches: list[BracketMatch],
    predictions: dict[str, tuple[int, int]],
) -> list[BracketTeam]:
    winners: list[BracketTeam] = []
    for m in matches:
        if not m.team_a or not m.team_b:
            continue
        if m.label in predictions:
            sa, sb = predictions[m.label]
            m.score_a, m.score_b = sa, sb
            m.winner = m.team_a if sa > sb else m.team_b if sb > sa else m.team_a
        if m.winner:
            winners.append(m.winner)
    return winners


def build_knockout_tree(
    r32: list[BracketMatch],
    rules: dict,
    r32_preds: dict[str, tuple[int, int]] | None = None,
    r16_preds: dict[str, tuple[int, int]] | None = None,
    qf_preds: dict[str, tuple[int, int]] | None = None,
    sf_preds: dict[str, tuple[int, int]] | None = None,
    final_pred: dict[str, tuple[int, int]] | None = None,
) -> dict:
    r32_preds = r32_preds or {}
    r16_preds = r16_preds or {}
    qf_preds = qf_preds or {}
    sf_preds = sf_preds or {}
    final_pred = final_pred or {}

    def _apply_preds(matches: list[BracketMatch], preds: dict[str, tuple[int, int]]) -> list[BracketTeam]:
        winners = []
        for m in matches:
            if m.label in preds and m.team_a and m.team_b:
                sa, sb = preds[m.label]
                m.score_a, m.score_b = sa, sb
                m.winner = m.team_a if sa >= sb else m.team_b
            elif m.team_a:
                m.winner = m.team_a
            if m.winner:
                winners.append(m.winner)
        return winners

    def _feeders_to_matches(feeders: list, winners_by_num: dict[int, BracketTeam]) -> list[BracketMatch]:
        result = []
        for f in feeders:
            ta = winners_by_num.get(f["feeder_a"])
            tb = winners_by_num.get(f["feeder_b"])
            result.append(
                BracketMatch(
                    label=f["bracket_slot"],
                    match_number=f["match_number"],
                    team_a=BracketTeam(ta.team_id, ta.team_name, ta.team_code, ta.source) if ta else None,
                    team_b=BracketTeam(tb.team_id, tb.team_name, tb.team_code, tb.source) if tb else None,
                )
            )
        return result

    r32_winners_list = _apply_preds(r32, r32_preds)
    winners_by_num: dict[int, BracketTeam] = {}
    for m, w in zip(r32, r32_winners_list):
        if m.match_number:
            winners_by_num[m.match_number] = w

    r16 = _feeders_to_matches(rules.get("r16_feeders", []), winners_by_num)
    r16_winners_list = _apply_preds(r16, r16_preds)
    winners_by_num_r16 = {m.match_number: w for m, w in zip(r16, r16_winners_list) if m.match_number}

    qf = _feeders_to_matches(rules.get("qf_feeders", []), winners_by_num_r16)
    qf_winners_list = _apply_preds(qf, qf_preds)
    winners_by_num_qf = {m.match_number: w for m, w in zip(qf, qf_winners_list) if m.match_number}

    sf = _feeders_to_matches(rules.get("sf_feeders", []), winners_by_num_qf)
    sf_winners_list = _apply_preds(sf, sf_preds)
    winners_by_num_sf = {m.match_number: w for m, w in zip(sf, sf_winners_list) if m.match_number}

    final = _feeders_to_matches(rules.get("final_feeders", []), winners_by_num_sf)
    _apply_preds(final, final_pred)

    def _serialize(matches: list[BracketMatch]) -> list[dict]:
        return [
            {
                "label": m.label,
                "match_number": m.match_number,
                "team_a": {"id": m.team_a.team_id, "name": m.team_a.team_name, "code": m.team_a.team_code}
                if m.team_a else None,
                "team_b": {"id": m.team_b.team_id, "name": m.team_b.team_name, "code": m.team_b.team_code}
                if m.team_b else None,
                "winner_id": m.winner.team_id if m.winner else None,
                "score_a": m.score_a,
                "score_b": m.score_b,
            }
            for m in matches
        ]

    return {"R32": _serialize(r32), "R16": _serialize(r16), "QF": _serialize(qf), "SF": _serialize(sf), "F": _serialize(final)}
