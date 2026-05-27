"""Load tournament data from JSON seed files."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Group,
    Match,
    MatchStage,
    MatchStatus,
    Stadium,
    Team,
    Tournament,
    TournamentSettings,
)

SEEDS_ROOT = Path(__file__).resolve().parent / "tournaments"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_seed_bundle(slug: str) -> dict:
    base = SEEDS_ROOT / slug
    bundle = {}
    for name in ["tournament", "groups", "teams", "stadiums", "matches", "knockout_rules"]:
        path = base / f"{name}.json"
        if path.exists():
            bundle[name] = json.loads(path.read_text())
    scenarios_path = base / "third_place_scenarios.json"
    if scenarios_path.exists():
        bundle["third_place_scenarios"] = json.loads(scenarios_path.read_text())
    return bundle


class TournamentImportError(Exception):
    pass


async def validate_seed_bundle(bundle: dict) -> list[str]:
    errors: list[str] = []
    teams = {t["code"] for t in bundle.get("teams", {}).get("teams", [])}
    for m in bundle.get("matches", {}).get("group_matches", []):
        if m["team_a_code"] not in teams:
            errors.append(f"Unknown team_a {m['team_a_code']} in match {m['match_number']}")
        if m["team_b_code"] not in teams:
            errors.append(f"Unknown team_b {m['team_b_code']} in match {m['match_number']}")
    stadium_keys = {s["key"] for s in bundle.get("stadiums", {}).get("stadiums", [])}
    for m in bundle.get("matches", {}).get("group_matches", []):
        if m.get("stadium_key") and m["stadium_key"] not in stadium_keys:
            errors.append(f"Unknown stadium {m['stadium_key']} in match {m['match_number']}")
    return errors


async def import_tournament(
    db: AsyncSession,
    slug: str,
    *,
    reset: bool = False,
    set_active: bool = True,
) -> dict:
    bundle = load_seed_bundle(slug)
    errors = await validate_seed_bundle(bundle)
    if errors:
        raise TournamentImportError("; ".join(errors))

    t_data = bundle["tournament"]
    existing = await db.execute(select(Tournament).where(Tournament.slug == slug))
    tournament = existing.scalar_one_or_none()

    if tournament and reset:
        await _clear_tournament_data(db, tournament.id)
        await db.flush()
    elif tournament and not reset:
        raise TournamentImportError(f"Tournament '{slug}' already exists. Use reset=true to reimport.")

    if not tournament:
        tournament = Tournament(
            slug=slug,
            name=t_data["name"],
            year=t_data["year"],
            format_type=t_data["format_type"],
            starts_at=_parse_dt(t_data.get("starts_at")),
            ends_at=_parse_dt(t_data.get("ends_at")),
            format_config=t_data.get("format_config", {}),
            is_active=False,
        )
        db.add(tournament)
        await db.flush()

    if set_active:
        others = await db.execute(select(Tournament).where(Tournament.id != tournament.id))
        for t in others.scalars():
            t.is_active = False
        tournament.is_active = True

    # Stadiums (global, upsert by key)
    stadium_map: dict[str, int] = {}
    for s in bundle["stadiums"]["stadiums"]:
        result = await db.execute(select(Stadium).where(Stadium.key == s["key"]))
        stadium = result.scalar_one_or_none()
        if not stadium:
            stadium = Stadium(
                key=s["key"],
                name=s["name"],
                city=s["city"],
                country=s["country"],
                timezone=s.get("timezone", "UTC"),
            )
            db.add(stadium)
            await db.flush()
        stadium_map[s["key"]] = stadium.id

    # Groups
    group_map: dict[str, int] = {}
    for g in bundle["groups"]["groups"]:
        grp = Group(tournament_id=tournament.id, name=g["name"], display_order=g.get("display_order", 0))
        db.add(grp)
        await db.flush()
        group_map[g["name"]] = grp.id

    # Teams
    team_map: dict[str, int] = {}
    for t in bundle["teams"]["teams"]:
        team = Team(
            tournament_id=tournament.id,
            group_id=group_map.get(t["group"]),
            name=t["name"],
            code=t["code"],
            group_name=t["group"],
            flag_code=t.get("flag_code"),
            confederation=t.get("confederation"),
            group_position=t.get("position"),
        )
        db.add(team)
        await db.flush()
        team_map[t["code"]] = team.id

    # Group matches
    match_order = 0
    for m in bundle["matches"]["group_matches"]:
        db.add(
            Match(
                tournament_id=tournament.id,
                stage=MatchStage.GROUP,
                group_name=m["group"],
                team_a_id=team_map[m["team_a_code"]],
                team_b_id=team_map[m["team_b_code"]],
                stadium_id=stadium_map.get(m.get("stadium_key")),
                kickoff_time_utc=_parse_dt(m.get("kickoff_utc")),
                match_number=m["match_number"],
                matchday=m.get("matchday"),
                stage_order=m.get("stage_order", match_order),
                status=MatchStatus.SCHEDULED,
                match_order=match_order,
            )
        )
        match_order += 1

    # Knockout matches from rules
    rules = bundle["knockout_rules"]
    placeholder_id = list(team_map.values())[0]
    stage_map = {"R32": MatchStage.R32, "R16": MatchStage.R16, "QF": MatchStage.QF, "SF": MatchStage.SF, "F": MatchStage.F}

    def _add_ko(entries: list, stage: MatchStage):
        nonlocal match_order
        for entry in entries:
            db.add(
                Match(
                    tournament_id=tournament.id,
                    stage=stage,
                    team_a_id=placeholder_id,
                    team_b_id=placeholder_id,
                    stadium_id=stadium_map.get(entry.get("stadium_key")),
                    kickoff_time_utc=_parse_dt(entry.get("kickoff_utc")),
                    match_number=entry["match_number"],
                    stage_order=entry["match_number"],
                    status=MatchStatus.SCHEDULED,
                    bracket_slot=entry["bracket_slot"],
                    feeder_a_match_number=entry.get("feeder_a"),
                    feeder_b_match_number=entry.get("feeder_b"),
                    match_order=match_order,
                )
            )
            match_order += 1

    _add_ko(rules.get("r32_fixed", []), MatchStage.R32)
    _add_ko(rules.get("r16_feeders", []), MatchStage.R16)
    _add_ko(rules.get("qf_feeders", []), MatchStage.QF)
    _add_ko(rules.get("sf_feeders", []), MatchStage.SF)
    _add_ko(rules.get("final_feeders", []), MatchStage.F)

    # Store knockout rules + scenarios in settings
    settings_result = await db.execute(
        select(TournamentSettings).where(TournamentSettings.tournament_id == tournament.id)
    )
    settings = settings_result.scalar_one_or_none()
    full_rules = {**rules, "third_place_scenarios": bundle.get("third_place_scenarios", [])}
    if not settings:
        settings = TournamentSettings(
            tournament_id=tournament.id,
            predictions_locked=False,
            tournament_started=False,
            knockout_rules_json=full_rules,
        )
        db.add(settings)
    else:
        settings.knockout_rules_json = full_rules

    await db.flush()
    match_count = await db.execute(select(Match).where(Match.tournament_id == tournament.id))
    return {
        "tournament_id": tournament.id,
        "slug": slug,
        "teams": len(team_map),
        "matches": len(match_count.scalars().all()),
        "groups": len(group_map),
        "stadiums": len(stadium_map),
    }


async def _clear_tournament_data(db: AsyncSession, tournament_id: int) -> None:
    await db.execute(delete(Match).where(Match.tournament_id == tournament_id))
    await db.execute(delete(Team).where(Team.tournament_id == tournament_id))
    await db.execute(delete(Group).where(Group.tournament_id == tournament_id))
    await db.execute(delete(TournamentSettings).where(TournamentSettings.tournament_id == tournament_id))


async def get_active_tournament(db: AsyncSession) -> Tournament | None:
    result = await db.execute(select(Tournament).where(Tournament.is_active == True).limit(1))  # noqa: E712
    return result.scalar_one_or_none()
