"""Per-user knockout tree must be fully resolved (no TBD) after all predictions."""

import json
from pathlib import Path

import pytest

from app.services.knockout_generator import build_knockout_tree, generate_r32_bracket, load_rules_from_dict
from app.services.user_tournament_simulation import validate_tree_no_tbd

SEEDS = Path(__file__).resolve().parent.parent / "app" / "seeds" / "tournaments" / "worldcup_2026"


@pytest.fixture
def rules():
    data = json.loads((SEEDS / "knockout_rules.json").read_text())
    data["third_place_scenarios"] = json.loads((SEEDS / "third_place_scenarios.json").read_text())
    return load_rules_from_dict(data)


def _minimal_qualifiers():
    qualifiers = {}
    for letter in "ABCDEFGHIJKL":
        qualifiers[letter] = [
            {"team_id": ord(letter) * 10 + 1, "team_name": f"W{letter}", "team_code": f"W{letter}", "position": 1},
            {"team_id": ord(letter) * 10 + 2, "team_name": f"R{letter}", "team_code": f"R{letter}", "position": 2},
        ]
    return qualifiers


def test_full_knockout_tree_no_tbd_with_all_preds(rules):
    from app.services.group_simulation import ThirdPlaceCandidate

    qualifiers = _minimal_qualifiers()
    third_ranked = [
        ThirdPlaceCandidate(
            ord(g) * 10 + 3, f"T{g}", f"T{g}", g, 3, 3, 2, 5
        )
        for g in ["A", "B", "C", "D", "E", "F", "G", "H"]
    ]
    r32 = generate_r32_bracket(qualifiers, third_ranked, rules)
    assert all(m.team_a and m.team_b for m in r32)

    all_labels: list[str] = []
    for m in r32:
        all_labels.append(m.label)
    for feeders_key, stage in [("r16_feeders", "R16"), ("qf_feeders", "QF"), ("sf_feeders", "SF"), ("final_feeders", "F")]:
        for f in rules.get(feeders_key, []):
            all_labels.append(f["bracket_slot"])

    preds = {label: (1, 0) for label in all_labels}
    r32p = {k: v for k, v in preds.items() if k.startswith("R32")}
    r16p = {k: v for k, v in preds.items() if k.startswith("R16")}
    qfp = {k: v for k, v in preds.items() if k.startswith("QF")}
    sfp = {k: v for k, v in preds.items() if k.startswith("SF")}
    finalp = {k: v for k, v in preds.items() if k.startswith("F")}

    tree = build_knockout_tree(
        r32,
        rules,
        r32_preds=r32p,
        r16_preds=r16p,
        qf_preds=qfp,
        sf_preds=sfp,
        final_pred=finalp,
    )
    validate_tree_no_tbd(tree)
    total = sum(len(tree.get(s, [])) for s in ("R32", "R16", "QF", "SF", "F"))
    assert total == 31


def test_preview_placeholders_fill_later_rounds(rules):
    qualifiers = _minimal_qualifiers()
    from app.services.group_simulation import ThirdPlaceCandidate

    third_ranked = [
        ThirdPlaceCandidate(ord(g) * 10 + 3, f"T{g}", f"T{g}", g, 3, 3, 2, 5)
        for g in ["A", "B", "C", "D", "E", "F", "G", "H"]
    ]
    r32 = generate_r32_bracket(qualifiers, third_ranked, rules)
    tree = build_knockout_tree(r32, rules, allow_placeholder_winners=True)
    validate_tree_no_tbd(tree)
