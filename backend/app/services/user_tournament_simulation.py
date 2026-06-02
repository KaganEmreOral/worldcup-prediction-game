"""Backwards-compatible re-exports — use user_prediction_tournament for Universe A."""

from app.services.bracket_participants import teams_in_round
from app.services.user_prediction_tournament import (
    STAGES as STAGES_ORDER,
    build_user_prediction_tournament as build_user_tournament_tree,
    load_user_prediction_tournament as load_user_bracket_tree,
    persist_user_prediction_tournament as persist_user_tournament_state,
    validate_bracket_no_tbd as validate_tree_no_tbd,
)

__all__ = [
    "STAGES_ORDER",
    "build_user_tournament_tree",
    "load_user_bracket_tree",
    "persist_user_tournament_state",
    "teams_in_round",
    "validate_tree_no_tbd",
]
