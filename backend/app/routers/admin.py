from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_admin
from app.database import get_db
from app.models import (
    GroupStandingsCache,
    KnockoutBracketCache,
    KnockoutPrediction,
    Match,
    MatchStage,
    MatchStatus,
    Prediction,
    SpecialPrediction,
    Team,
    Tournament,
    TournamentSettings,
    User,
    UserKnockoutBracket,
)
from app.schemas import MatchCreate, MatchUpdate, TournamentImportRequest, TournamentSettingsResponse, TournamentSettingsUpdate
from app.seeds.tournament_loader import TournamentImportError, get_active_tournament, import_tournament, load_seed_bundle, validate_seed_bundle
from app.services.group_simulation import MatchResult, compute_group_standings, get_qualified_teams, rank_third_place_teams
from app.services.knockout_generator import generate_r32_bracket
from app.services.match_scoring import on_match_result_updated
from app.services.recalculation import recalculate_all
from app.services.tournament_state import recompute_tournament_state, reset_all_match_results
from app.services.tournament_config import get_knockout_rules

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _get_settings(db: AsyncSession) -> TournamentSettings | None:
    tournament = await get_active_tournament(db)
    if tournament:
        result = await db.execute(
            select(TournamentSettings).where(TournamentSettings.tournament_id == tournament.id)
        )
        return result.scalar_one_or_none()
    result = await db.execute(select(TournamentSettings).limit(1))
    return result.scalar_one_or_none()


@router.get("/users")
async def list_users(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()
    out = []
    for u in users:
        pred_count = await db.execute(select(Prediction).where(Prediction.user_id == u.id))
        out.append({
            "id": u.id,
            "username": u.username,
            "name": u.name,
            "is_admin": u.is_admin,
            "prediction_count": len(pred_count.scalars().all()),
            "created_at": u.created_at.isoformat(),
        })
    return out


@router.post("/users/{user_id}/rebuild-bracket")
async def rebuild_user_bracket(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Rebuild per-user R32→Final bracket from stored predictions (fixes empty 3rd-place slots)."""
    from app.services.prediction_validation import load_group_matches, load_knockout_matches, load_teams_by_group
    from app.services.user_prediction_tournament import persist_user_prediction_tournament

    pred_result = await db.execute(select(Prediction).where(Prediction.user_id == user_id))
    predictions = {p.match_id: (p.predicted_score_a, p.predicted_score_b) for p in pred_result.scalars()}
    if not predictions:
        raise HTTPException(status_code=400, detail="User has no group predictions")

    ko_result = await db.execute(select(KnockoutPrediction).where(KnockoutPrediction.user_id == user_id))
    ko_list = ko_result.scalars().all()
    if len(ko_list) < 31:
        raise HTTPException(status_code=400, detail="User has incomplete knockout predictions")

    ko_map = {kp.bracket_slot: (kp.predicted_score_a, kp.predicted_score_b) for kp in ko_list}
    group_matches = await load_group_matches(db)
    knockout_matches = await load_knockout_matches(db)
    teams_by_group = await load_teams_by_group(db)

    try:
        state = await persist_user_prediction_tournament(
            db,
            user_id,
            group_matches,
            knockout_matches,
            predictions,
            ko_map,
            teams_by_group,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.flush()
    r32 = state["bracket_tree"].get("R32", [])
    return {
        "message": f"Bracket rebuilt for user {user_id}",
        "state_hash": state["state_hash"],
        "r32_matches": len(r32),
        "r32_filled": sum(1 for m in r32 if m.get("team_a") and m.get("team_b")),
    }


@router.post("/users/{user_id}/reset-predictions")
async def reset_user_predictions(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(Prediction).where(Prediction.user_id == user_id))
    await db.execute(delete(KnockoutPrediction).where(KnockoutPrediction.user_id == user_id))
    await db.execute(delete(SpecialPrediction).where(SpecialPrediction.user_id == user_id))
    await db.execute(delete(GroupStandingsCache).where(GroupStandingsCache.user_id == user_id))
    await db.execute(delete(KnockoutBracketCache).where(KnockoutBracketCache.user_id == user_id))
    await db.execute(delete(UserKnockoutBracket).where(UserKnockoutBracket.user_id == user_id))
    await db.flush()
    recompute = await recompute_tournament_state(db, trigger_source="admin_reset_user_predictions")
    return {
        "message": f"Predictions reset for user {user_id}",
        "recompute": recompute,
        "leaderboard": recompute.get("leaderboard", []),
    }


@router.post("/reset-match-results")
async def reset_match_results_endpoint(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Clear all real match results and rebuild leaderboard / homepage projections."""
    return await reset_all_match_results(db)


@router.get("/matches/audit")
async def admin_matches_audit(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Expected vs actual match counts for admin dashboard."""
    from app.seeds.tournament_loader import load_seed_bundle

    tournament = await get_active_tournament(db)
    bundle = load_seed_bundle("worldcup_2026")
    seed_group = len(bundle["matches"]["group_matches"])
    seed_ko = sum(
        len(bundle["knockout_rules"].get(k, []))
        for k in ("r32_fixed", "r16_feeders", "qf_feeders", "sf_feeders", "final_feeders")
    )

    q = select(Match)
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    all_m = (await db.execute(q)).scalars().all()
    by_stage: dict[str, int] = {}
    for m in all_m:
        by_stage[m.stage.value] = by_stage.get(m.stage.value, 0) + 1
    group_nums = sorted(m.match_number for m in all_m if m.stage == MatchStage.GROUP and m.match_number)
    missing_nums = sorted(set(range(1, 73)) - set(group_nums)) if group_nums else list(range(1, 73))

    return {
        "seed": {"group": seed_group, "knockout": seed_ko, "total": seed_group + seed_ko},
        "database": {"by_stage": by_stage, "total": len(all_m)},
        "group_match_numbers": {"count": len(group_nums), "missing": missing_nums},
        "group_complete": len(group_nums) == 72 and not missing_nums,
    }


@router.get("/matches")
async def admin_list_matches(
    stage: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    tournament = await get_active_tournament(db)
    q = select(Match).options(selectinload(Match.team_a), selectinload(Match.team_b))
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    if stage:
        q = q.where(Match.stage == MatchStage(stage))
    q = q.order_by(Match.match_order, Match.match_number, Match.id)
    result = await db.execute(q)
    matches = result.scalars().unique().all()
    return [
        {
            "id": m.id,
            "stage": m.stage.value,
            "group_name": m.group_name,
            "team_a_id": m.team_a_id,
            "team_b_id": m.team_b_id,
            "team_a_name": m.team_a.name if m.team_a else None,
            "team_b_name": m.team_b.name if m.team_b else None,
            "real_score_a": m.real_score_a,
            "real_score_b": m.real_score_b,
            "status": m.status.value,
            "bracket_slot": m.bracket_slot,
            "match_order": m.match_order,
        }
        for m in matches
    ]


@router.post("/matches")
async def create_match(
    data: MatchCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    match = Match(
        stage=MatchStage(data.stage),
        group_name=data.group_name,
        team_a_id=data.team_a_id,
        team_b_id=data.team_b_id,
        bracket_slot=data.bracket_slot,
        match_order=data.match_order,
    )
    db.add(match)
    await db.flush()
    await db.refresh(match)
    return {"id": match.id}


@router.patch("/matches/{match_id}")
async def update_match(
    match_id: int,
    data: MatchUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Match).where(Match.id == match_id))
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    if data.real_score_a is not None:
        match.real_score_a = data.real_score_a
    if data.real_score_b is not None:
        match.real_score_b = data.real_score_b
    if data.status is not None:
        match.status = MatchStatus(data.status)
        if data.status == "finished" and match.real_score_a is not None:
            pass
    if data.team_a_id is not None:
        match.team_a_id = data.team_a_id
    if data.team_b_id is not None:
        match.team_b_id = data.team_b_id

    if match.real_score_a is not None and match.real_score_b is not None:
        match.status = MatchStatus.FINISHED

    await db.flush()

    scoring_result = None
    if match.real_score_a is not None and match.real_score_b is not None:
        scoring_result = await on_match_result_updated(db, match, trigger="admin_save")

    return {
        "message": "Match updated",
        "id": match.id,
        "scoring": scoring_result,
    }


@router.get("/settings")
async def get_settings(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    settings = await _get_settings(db)
    tournament = await get_active_tournament(db)
    if not settings:
        return TournamentSettingsResponse(
            predictions_locked=False, tournament_started=False,
            actual_top_scorer=None, actual_top_assister=None,
        )
    return {
        **TournamentSettingsResponse(
            predictions_locked=settings.predictions_locked,
            tournament_started=settings.tournament_started,
            actual_top_scorer=settings.actual_top_scorer,
            actual_top_assister=settings.actual_top_assister,
        ).model_dump(),
        "tournament": {"slug": tournament.slug, "name": tournament.name} if tournament else None,
    }


@router.patch("/settings")
async def update_settings(
    data: TournamentSettingsUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    settings = await _get_settings(db)
    tournament = await get_active_tournament(db)
    if not settings:
        settings = TournamentSettings(tournament_id=tournament.id if tournament else None)
        db.add(settings)
    if data.predictions_locked is not None:
        settings.predictions_locked = data.predictions_locked
    if data.tournament_started is not None:
        settings.tournament_started = data.tournament_started
    if data.actual_top_scorer is not None:
        settings.actual_top_scorer = data.actual_top_scorer
    if data.actual_top_assister is not None:
        settings.actual_top_assister = data.actual_top_assister
    await db.flush()

    scoring_result = None
    if data.actual_top_scorer is not None or data.actual_top_assister is not None:
        scoring_result = await recompute_tournament_state(db, trigger_source="admin_special_settings")

    return {"message": "Settings updated", "scoring": scoring_result}


@router.post("/recalculate")
async def trigger_recalculation(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await recompute_tournament_state(db, trigger_source="admin_manual_recalculate")
    return result


@router.post("/teams")
async def create_team(
    name: str,
    code: str,
    group_name: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    team = Team(name=name, code=code.upper(), group_name=group_name)
    db.add(team)
    await db.flush()
    return {"id": team.id, "name": team.name, "code": team.code}


@router.post("/import-tournament")
async def import_tournament_endpoint(
    data: TournamentImportRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await import_tournament(
            db, data.slug, reset=data.reset, set_active=data.set_active
        )
        return {"message": "Tournament imported", **result}
    except TournamentImportError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tournament/validate")
async def validate_tournament(
    slug: str = "worldcup_2026",
    admin: User = Depends(require_admin),
):
    bundle = load_seed_bundle(slug)
    errors = await validate_seed_bundle(bundle)
    return {"valid": len(errors) == 0, "errors": errors, "slug": slug}


@router.post("/tournament/populate-knockout")
async def populate_knockout_bracket(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Fill knockout match team slots from real group-stage results (Universe B)."""
    from app.services.real_tournament_state import build_real_tournament_bracket, persist_real_tournament_state

    tournament = await get_active_tournament(db)
    q = select(Team)
    mq = select(Match)
    if tournament:
        q = q.where(Team.tournament_id == tournament.id)
        mq = mq.where(Match.tournament_id == tournament.id)
    teams = (await db.execute(q)).scalars().all()
    all_matches = (await db.execute(mq)).scalars().all()
    group_matches = [m for m in all_matches if m.stage == MatchStage.GROUP]
    knockout_matches = [m for m in all_matches if m.stage != MatchStage.GROUP]

    teams_by_group: dict[str, list] = {}
    for t in teams:
        if t.group_name:
            teams_by_group.setdefault(t.group_name, []).append((t.id, t.name, t.code))

    rules = await get_knockout_rules(db)
    _, tree = build_real_tournament_bracket(teams_by_group, group_matches, knockout_matches, rules)
    if not tree:
        raise HTTPException(status_code=400, detail="Enter all group-stage results before generating knockout bracket")

    label_to_teams: dict[str, tuple[int | None, int | None]] = {}
    for stage_matches in tree.values():
        for m in stage_matches:
            ta = m.get("team_a", {}) or {}
            tb = m.get("team_b", {}) or {}
            label_to_teams[m["label"]] = (ta.get("id"), tb.get("id"))

    updated = 0
    for m in knockout_matches:
        if not m.bracket_slot:
            continue
        pair = label_to_teams.get(m.bracket_slot)
        if not pair:
            continue
        ta_id, tb_id = pair
        if ta_id and tb_id:
            m.team_a_id = ta_id
            m.team_b_id = tb_id
            updated += 1

    if tournament:
        await persist_real_tournament_state(
            db, tournament.id, teams_by_group, group_matches, knockout_matches, rules
        )
    await db.flush()
    return {
        "message": f"Updated {updated} knockout matches from real group results",
        "bracket_stages": list(tree.keys()),
        "universe": "real_tournament_state",
    }


@router.get("/tournament/preview-bracket")
async def preview_bracket(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Preview R32 bracket using real group results entered so far."""
    tournament = await get_active_tournament(db)
    q = select(Team)
    mq = select(Match).where(Match.stage == MatchStage.GROUP)
    if tournament:
        q = q.where(Team.tournament_id == tournament.id)
        mq = mq.where(Match.tournament_id == tournament.id)
    teams = (await db.execute(q)).scalars().all()
    group_matches = (await db.execute(mq)).scalars().all()
    teams_by_group: dict[str, list] = {}
    for t in teams:
        if t.group_name:
            teams_by_group.setdefault(t.group_name, []).append((t.id, t.name, t.code))
    all_standings = {}
    for group_name, team_list in teams_by_group.items():
        results = []
        for m in group_matches:
            if m.group_name == group_name and m.real_score_a is not None:
                results.append(MatchResult(m.team_a_id, m.team_b_id, m.real_score_a, m.real_score_b))
        if results:
            all_standings[group_name] = compute_group_standings(team_list, results)
    if not all_standings:
        return {"message": "No finished group matches yet", "r32": []}
    qualifiers = get_qualified_teams(all_standings)
    third_ranked = rank_third_place_teams(all_standings)
    rules = await get_knockout_rules(db)
    r32 = generate_r32_bracket(qualifiers, third_ranked, rules)
    return {
        "qualifiers": qualifiers,
        "r32": [
            {
                "label": m.label,
                "match_number": m.match_number,
                "team_a": m.team_a.team_code if m.team_a else None,
                "team_b": m.team_b.team_code if m.team_b else None,
            }
            for m in r32
        ],
    }


@router.get("/tournaments")
async def list_tournaments(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tournament).order_by(Tournament.year.desc()))
    return [
        {"id": t.id, "slug": t.slug, "name": t.name, "year": t.year, "is_active": t.is_active}
        for t in result.scalars()
    ]


# --- Testing utilities (disable in production via ENABLE_TESTING_TOOLS=false) ---

from app.config import settings as app_settings
import random


def _require_testing():
    if not app_settings.enable_testing_tools:
        raise HTTPException(status_code=403, detail="Testing tools disabled")


@router.post("/testing/fill-random-results")
async def fill_random_results(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    _require_testing()
    tournament = await get_active_tournament(db)
    q = select(Match).where(Match.stage == MatchStage.GROUP, Match.real_score_a.is_(None))
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    matches = (await db.execute(q)).scalars().all()
    count = 0
    for m in matches:
        m.real_score_a = random.randint(0, 4)
        m.real_score_b = random.randint(0, 4)
        m.status = MatchStatus.FINISHED
        count += 1
    await db.flush()
    if count:
        result = await recalculate_all(db, trigger_source="testing_fill_random")
        return {"message": f"Filled {count} random results", "scoring": result}
    return {"message": f"Filled {count} random results", "scoring": None}


@router.post("/testing/simulate-matchday")
async def simulate_matchday(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    _require_testing()
    tournament = await get_active_tournament(db)
    q = select(Match).where(Match.stage == MatchStage.GROUP, Match.real_score_a.is_(None))
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    q = q.order_by(Match.matchday, Match.match_number).limit(24)
    matches = (await db.execute(q)).scalars().all()
    for m in matches:
        m.real_score_a = random.randint(0, 3)
        m.real_score_b = random.randint(0, 3)
        m.status = MatchStatus.FINISHED
    await db.flush()
    result = await recalculate_all(db, trigger_source="testing_simulate_matchday")
    return {"message": f"Simulated {len(matches)} matches", "scoring": result}


@router.post("/testing/generate-demo-users")
async def generate_demo_users(
    count: int = 10,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    _require_testing()
    from app.auth.security import hash_password

    created = []
    for i in range(count):
        uname = f"demo{i+1}"
        existing = await db.execute(select(User).where(User.username == uname))
        if existing.scalar_one_or_none():
            continue
        db.add(User(username=uname, name=f"Demo Player {i+1}", password_hash=hash_password("demo123")))
        created.append(uname)
    await db.flush()
    return {"message": f"Created {len(created)} demo users", "usernames": created, "password": "demo123"}
