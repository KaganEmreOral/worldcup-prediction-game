"""Shared helpers for reading team sets from serialized bracket trees."""

STAGES = ("R32", "R16", "QF", "SF", "F")


def teams_in_round(bracket_tree: dict, stage: str) -> set[int]:
    """All team ids appearing in fixtures for a stage (participation set)."""
    ids: set[int] = set()
    for m in bracket_tree.get(stage, []):
        ta, tb = m.get("team_a"), m.get("team_b")
        if ta and ta.get("id"):
            ids.add(ta["id"])
        if tb and tb.get("id"):
            ids.add(tb["id"])
    return ids


def champion_team_id(bracket_tree: dict) -> int | None:
    finals = bracket_tree.get("F", [])
    if not finals:
        return None
    return finals[0].get("winner_id")
