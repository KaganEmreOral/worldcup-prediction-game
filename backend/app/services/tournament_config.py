"""Helpers for loading active tournament configuration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tournament, TournamentSettings
from app.seeds.tournament_loader import get_active_tournament, load_seed_bundle


def _merge_third_place_scenarios(rules: dict, slug: str = "worldcup_2026") -> dict:
    """Ensure third_place_scenarios are present (required for R32 3rd-place slots)."""
    if rules.get("third_place_scenarios"):
        return rules
    bundle = load_seed_bundle(slug)
    merged = {**rules, "third_place_scenarios": bundle.get("third_place_scenarios", [])}
    return merged


async def get_knockout_rules(db: AsyncSession) -> dict:
    tournament = await get_active_tournament(db)
    slug = tournament.slug if tournament and tournament.slug else "worldcup_2026"
    if tournament:
        settings_result = await db.execute(
            select(TournamentSettings).where(TournamentSettings.tournament_id == tournament.id)
        )
        settings = settings_result.scalar_one_or_none()
        if settings and settings.knockout_rules_json:
            return _merge_third_place_scenarios(settings.knockout_rules_json, slug)
        if tournament.slug:
            bundle = load_seed_bundle(tournament.slug)
            rules = bundle.get("knockout_rules", {})
            rules["third_place_scenarios"] = bundle.get("third_place_scenarios", [])
            return rules
    bundle = load_seed_bundle("worldcup_2026")
    rules = bundle.get("knockout_rules", {})
    rules["third_place_scenarios"] = bundle.get("third_place_scenarios", [])
    return rules


async def get_format_config(db: AsyncSession) -> dict:
    tournament = await get_active_tournament(db)
    if tournament and tournament.format_config:
        return tournament.format_config
    return {"best_third_count": 8, "groups_count": 12, "teams_per_group": 4}
