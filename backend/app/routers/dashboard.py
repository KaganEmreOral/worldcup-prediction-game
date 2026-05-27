from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_optional_user
from app.database import get_db
from app.models import Match, MatchStage, MatchStatus, Prediction, SpecialPrediction, Team, User, UserScore, KnockoutPrediction
from app.services.cache import cached
from app.services.group_simulation import MatchResult, compute_group_standings
from app.seeds.tournament_loader import get_active_tournament

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _compute_real_standings(teams_by_group: dict, group_matches: list) -> dict[str, list]:
    all_standings = {}
    for group_name, team_list in teams_by_group.items():
        results = []
        for m in group_matches:
            if m.group_name == group_name and m.real_score_a is not None:
                results.append(MatchResult(m.team_a_id, m.team_b_id, m.real_score_a, m.real_score_b))
        if results:
            all_standings[group_name] = [s.to_dict() for s in compute_group_standings(team_list, results)]
        else:
            all_standings[group_name] = [
                {"team_id": t[0], "team_name": t[1], "team_code": t[2], "played": 0, "points": 0,
                 "goal_difference": 0, "goals_for": 0, "goals_against": 0}
                for t in team_list
            ]
    return all_standings


@router.get("")
async def get_dashboard(db: AsyncSession = Depends(get_db), user: User | None = Depends(get_optional_user)):
    tournament = await get_active_tournament(db)

    def _load():
        return {"tournament_id": tournament.id if tournament else None}

    cached("dashboard:meta", 60, _load)

    q_teams = select(Team).order_by(Team.group_name, Team.group_position)
    if tournament:
        q_teams = q_teams.where(Team.tournament_id == tournament.id)
    teams = (await db.execute(q_teams)).scalars().all()
    teams_by_group: dict[str, list] = {}
    team_flags: dict[str, str] = {}
    for t in teams:
        if t.group_name:
            teams_by_group.setdefault(t.group_name, []).append((t.id, t.name, t.code))
            team_flags[t.code] = t.flag_code or ""

    mq = select(Match).options(
        selectinload(Match.team_a), selectinload(Match.team_b), selectinload(Match.stadium)
    )
    if tournament:
        mq = mq.where(Match.tournament_id == tournament.id)
    all_matches = (await db.execute(mq)).scalars().all()
    group_matches = [m for m in all_matches if m.stage == MatchStage.GROUP]

    standings = cached(
        f"standings:{tournament.id if tournament else 0}",
        30,
        lambda: _compute_real_standings(teams_by_group, group_matches),
    )

    now = datetime.now(timezone.utc)
    finished = [m for m in all_matches if m.status == MatchStatus.FINISHED]
    finished.sort(key=lambda m: m.kickoff_time_utc or now, reverse=True)
    upcoming = [m for m in all_matches if m.status == MatchStatus.SCHEDULED and m.kickoff_time_utc]
    upcoming.sort(key=lambda m: m.kickoff_time_utc or now)

    def _match_brief(m: Match) -> dict:
        return {
            "id": m.id,
            "match_number": m.match_number,
            "stage": m.stage.value,
            "group_name": m.group_name,
            "team_a_code": m.team_a.code if m.team_a else None,
            "team_b_code": m.team_b.code if m.team_b else None,
            "team_a_flag": m.team_a.flag_code if m.team_a else None,
            "team_b_flag": m.team_b.flag_code if m.team_b else None,
            "real_score_a": m.real_score_a,
            "real_score_b": m.real_score_b,
            "kickoff_time_utc": m.kickoff_time_utc.isoformat() if m.kickoff_time_utc else None,
            "stadium": {"name": m.stadium.name, "city": m.stadium.city} if m.stadium else None,
        }

    lb_result = await db.execute(
        select(UserScore, User).join(User, UserScore.user_id == User.id).order_by(UserScore.total_score.desc()).limit(10)
    )
    top_leaderboard = [
        {"rank": i + 1, "name": u.name, "username": u.username, "total_score": s.total_score}
        for i, (s, u) in enumerate(lb_result.all())
    ]

    pred_count = await db.execute(select(func.count(Prediction.id)))
    users_with_preds = await db.execute(select(func.count(func.distinct(Prediction.user_id))))

    sp_result = await db.execute(select(SpecialPrediction))
    special_preds = sp_result.scalars().all()
    champion_counts: dict[str, int] = {}
    scorer_counts: dict[str, int] = {}
    for sp in special_preds:
        if sp.top_scorer:
            scorer_counts[sp.top_scorer] = scorer_counts.get(sp.top_scorer, 0) + 1

    ko_final = await db.execute(
        select(KnockoutPrediction, Team)
        .outerjoin(Team, Team.id == KnockoutPrediction.sim_team_a_id)
        .where(KnockoutPrediction.stage == MatchStage.F)
    )
    team_cache: dict[int, str] = {t.id: t.name for t in teams}
    for kp, _ in ko_final.all():
        winner_id = None
        if kp.predicted_score_a > kp.predicted_score_b:
            winner_id = kp.sim_team_a_id
        elif kp.predicted_score_b > kp.predicted_score_a:
            winner_id = kp.sim_team_b_id
        if winner_id and winner_id in team_cache:
            name = team_cache[winner_id]
            champion_counts[name] = champion_counts.get(name, 0) + 1

    user_score_map: dict[int, float] = {}
    if user:
        us = await db.execute(select(UserScore).where(UserScore.user_id == user.id))
        row = us.scalar_one_or_none()
        if row and row.breakdown_json:
            user_score_map = {m["match_id"]: m for m in row.breakdown_json.get("match_scores", []) if "match_id" in m}

    latest = []
    for m in finished[:8]:
        brief = _match_brief(m)
        if user and m.id in user_score_map:
            brief["scoring"] = user_score_map[m.id]
        latest.append(brief)

    return {
        "standings": standings,
        "team_flags": team_flags,
        "latest_results": latest,
        "upcoming_fixtures": [_match_brief(m) for m in upcoming[:8]],
        "leaderboard": top_leaderboard,
        "stats": {
            "total_predictions": pred_count.scalar() or 0,
            "users_with_predictions": users_with_preds.scalar() or 0,
            "most_predicted_champion": max(champion_counts, key=champion_counts.get) if champion_counts else None,
            "champion_pick_count": max(champion_counts.values()) if champion_counts else 0,
            "most_predicted_scorer": max(scorer_counts, key=scorer_counts.get) if scorer_counts else None,
            "scorer_pick_count": max(scorer_counts.values()) if scorer_counts else 0,
            "finished_matches": len(finished),
            "total_matches": len(all_matches),
        },
    }
