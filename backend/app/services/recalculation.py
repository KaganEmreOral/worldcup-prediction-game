"""Full recalculation pipeline for all users."""

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    GroupStandingsCache,
    KnockoutBracketCache,
    KnockoutPrediction,
    LeaderboardSnapshot,
    Match,
    MatchStage,
    Prediction,
    SpecialPrediction,
    Team,
    TournamentSettings,
    User,
    UserMatchScore,
    UserScore,
)
from app.services.cache import invalidate
from app.services.group_simulation import MatchResult, compute_group_standings
from app.services.knockout_scoring import (
    build_real_knockout_tree,
    build_user_knockout_tree,
    real_knockout_preds_from_matches,
    score_knockout_exact_bonuses,
    score_knockout_progression,
)
from app.services.scoring_engine import (
    ScoreBreakdown,
    build_match_score_entry,
    score_group_match,
    score_qualification,
    simulate_real_groups,
    simulate_user_groups,
    _enrich_detail,
)
from app.services.tournament_config import get_knockout_rules

logger = logging.getLogger(__name__)


async def _load_teams_by_group(db: AsyncSession) -> dict[str, list[tuple[int, str, str]]]:
    from app.seeds.tournament_loader import get_active_tournament

    tournament = await get_active_tournament(db)
    q = select(Team).order_by(Team.group_name, Team.name)
    if tournament:
        q = q.where(Team.tournament_id == tournament.id)
    teams = (await db.execute(q)).scalars().all()
    by_group: dict[str, list] = {}
    for t in teams:
        if t.group_name:
            by_group.setdefault(t.group_name, []).append((t.id, t.name, t.code))
    return by_group


async def recalculate_all(
    db: AsyncSession,
    *,
    trigger_match_id: int | None = None,
    trigger_source: str = "manual",
    skip_derived_clear: bool = False,
) -> dict:
    from app.seeds.tournament_loader import get_active_tournament

    logger.info(
        "recalculate.start trigger_match_id=%s source=%s",
        trigger_match_id,
        trigger_source,
    )

    if not skip_derived_clear:
        invalidate(None)
    else:
        invalidate("dashboard")
        invalidate("standings")

    tournament = await get_active_tournament(db)
    teams_by_group = await _load_teams_by_group(db)

    q = select(Match).options(selectinload(Match.team_a), selectinload(Match.team_b))
    if tournament:
        q = q.where(Match.tournament_id == tournament.id)
    all_matches = (await db.execute(q)).scalars().all()
    group_matches = [m for m in all_matches if m.stage == MatchStage.GROUP]
    knockout_matches = [m for m in all_matches if m.stage != MatchStage.GROUP]

    settings_result = await db.execute(select(TournamentSettings))
    all_settings = settings_result.scalars().all()
    settings = None
    if tournament:
        settings = next((s for s in all_settings if s.tournament_id == tournament.id), None)
    if not settings and all_settings:
        settings = all_settings[0]

    users_result = await db.execute(select(User))
    users = users_result.scalars().all()

    real_qualifiers = simulate_real_groups(teams_by_group, group_matches)
    rules = await get_knockout_rules(db)
    real_ko_preds_map = real_knockout_preds_from_matches(knockout_matches)
    real_tree = build_real_knockout_tree(teams_by_group, group_matches, real_ko_preds_map, rules)

    leaderboard = []
    recent_events: list[dict] = []

    if skip_derived_clear:
        await db.execute(delete(GroupStandingsCache))
        await db.execute(delete(KnockoutBracketCache))
        await db.execute(delete(UserMatchScore))
    else:
        from app.services.tournament_state import clear_derived_state

        await clear_derived_state(db)

    predictions_count = 0
    for user in users:
        pred_result = await db.execute(select(Prediction).where(Prediction.user_id == user.id))
        predictions = {p.match_id: (p.predicted_score_a, p.predicted_score_b) for p in pred_result.scalars()}
        if predictions:
            predictions_count += 1

        breakdown = ScoreBreakdown()

        for m in group_matches:
            if m.id not in predictions or m.real_score_a is None:
                continue
            pa, pb = predictions[m.id]
            pts, det = score_group_match(pa, pb, m.real_score_a, m.real_score_b)
            breakdown.group_match_points += pts
            breakdown.details.extend(det)
            entry = build_match_score_entry(m, pa, pb, m.real_score_a, m.real_score_b, pts, det)
            breakdown.match_scores.append(entry)
            if pts > 0:
                recent_events.append({**entry, "user_name": user.name, "user_id": user.id})

        user_qualifiers = simulate_user_groups(teams_by_group, predictions, group_matches)

        for group_name, team_list in teams_by_group.items():
            results = []
            for m in group_matches:
                if m.group_name == group_name and m.id in predictions:
                    sa, sb = predictions[m.id]
                    results.append(MatchResult(m.team_a_id, m.team_b_id, sa, sb))
            if results:
                standings = compute_group_standings(team_list, results)
                db.add(
                    GroupStandingsCache(
                        user_id=user.id,
                        group_name=group_name,
                        standings_json=[s.to_dict() for s in standings],
                        qualified_teams=user_qualifiers.get(group_name, []),
                    )
                )

        if real_qualifiers:
            qp, wp, fb, det = score_qualification(user_qualifiers, real_qualifiers)
            breakdown.qualification_points = qp
            breakdown.group_winner_points = wp
            breakdown.full_group_bonus = fb
            breakdown.details.extend(det)

        ko_pred_result = await db.execute(
            select(KnockoutPrediction).where(KnockoutPrediction.user_id == user.id)
        )
        user_ko_list = list(ko_pred_result.scalars().all())
        user_ko_preds = {kp.bracket_slot: kp for kp in user_ko_list}
        user_ko_score_map = {
            kp.bracket_slot: (kp.predicted_score_a, kp.predicted_score_b) for kp in user_ko_list
        }

        if real_tree and predictions:
            user_tree = build_user_knockout_tree(
                teams_by_group, predictions, group_matches, user_ko_score_map, rules
            )
            kp_pts, kp_det = score_knockout_progression(user_tree, real_tree)
            breakdown.knockout_progression_points += kp_pts
            breakdown.details.extend(kp_det)

        ke_pts, ke_det = score_knockout_exact_bonuses(user_ko_preds, knockout_matches)
        breakdown.knockout_exact_points += ke_pts
        breakdown.details.extend(ke_det)

        for slot, m in {m.bracket_slot: m for m in knockout_matches if m.bracket_slot}.items():
            kp = user_ko_preds.get(slot)
            if not kp or m.real_score_a is None:
                continue
            pts = sum(d.get("points", 0) for d in ke_det if d.get("bracket_slot") == slot)
            if pts > 0:
                entry = build_match_score_entry(
                    m, kp.predicted_score_a, kp.predicted_score_b, m.real_score_a, m.real_score_b,
                    pts, [], bracket_slot=slot,
                )
                breakdown.match_scores.append(entry)
                recent_events.append({**entry, "user_name": user.name, "user_id": user.id})

        sp_result = await db.execute(select(SpecialPrediction).where(SpecialPrediction.user_id == user.id))
        sp = sp_result.scalar_one_or_none()
        if sp and settings:
            if settings.actual_top_scorer and sp.top_scorer == settings.actual_top_scorer:
                breakdown.special_points += 20
                breakdown.details.append(_enrich_detail({"type": "top_scorer", "points": 20}))
            if settings.actual_top_assister and sp.top_assister == settings.actual_top_assister:
                breakdown.special_points += 20
                breakdown.details.append(_enrich_detail({"type": "top_assister", "points": 20}))

        score_result = await db.execute(select(UserScore).where(UserScore.user_id == user.id))
        user_score = score_result.scalar_one_or_none()
        if not user_score:
            user_score = UserScore(user_id=user.id)
            db.add(user_score)

        user_score.group_score = breakdown.group_total - breakdown.qualification_points - breakdown.group_winner_points - breakdown.full_group_bonus
        user_score.qualification_score = breakdown.qualification_points + breakdown.group_winner_points + breakdown.full_group_bonus
        user_score.knockout_score = breakdown.knockout_total
        user_score.special_score = breakdown.special_points
        user_score.chain_bonus = 0
        user_score.total_score = breakdown.total
        user_score.breakdown_json = {
            "group_match": breakdown.group_match_points,
            "qualification": breakdown.qualification_points,
            "group_winner": breakdown.group_winner_points,
            "full_group_bonus": breakdown.full_group_bonus,
            "knockout_progression": breakdown.knockout_progression_points,
            "knockout_exact": breakdown.knockout_exact_points,
            "special": breakdown.special_points,
            "details": [_enrich_detail(d) if "label" not in d else d for d in breakdown.details[:200]],
            "match_scores": breakdown.match_scores,
        }
        user_score.updated_at = datetime.now(timezone.utc)

        from app.services.match_scoring import sync_user_match_scores

        await sync_user_match_scores(db, user.id, breakdown.match_scores)

        leaderboard.append({
            "user_id": user.id,
            "name": user.name,
            "username": user.username,
            "total_score": breakdown.total,
            "group_score": breakdown.group_total,
            "knockout_score": breakdown.knockout_total,
            "special_score": breakdown.special_points,
        })

    leaderboard.sort(key=lambda x: -x["total_score"])

    prev_result = await db.execute(
        select(LeaderboardSnapshot).order_by(LeaderboardSnapshot.snapshot_date.desc()).limit(1)
    )
    prev = prev_result.scalar_one_or_none()
    prev_ranks = {}
    prev_scores = {}
    if prev:
        for i, row in enumerate(prev.rankings_json):
            prev_ranks[row["user_id"]] = i + 1
            prev_scores[row["user_id"]] = row.get("total_score", 0)

    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1
        uid = entry["user_id"]
        if uid in prev_ranks:
            entry["rank_change"] = prev_ranks[uid] - entry["rank"]
            entry["daily_points"] = round(entry["total_score"] - prev_scores.get(uid, 0), 1)
        else:
            entry["rank_change"] = None
            entry["daily_points"] = entry["total_score"]

    snapshot = LeaderboardSnapshot(
        snapshot_date=datetime.now(timezone.utc),
        rankings_json=leaderboard,
    )
    db.add(snapshot)

    recent_events.sort(key=lambda x: -x.get("points", 0))
    await db.flush()

    logger.info(
        "recalculate.done users=%s with_predictions=%s leaderboard_size=%s events=%s",
        len(users),
        predictions_count,
        len(leaderboard),
        len(recent_events),
    )

    return {
        "users_scored": len(users),
        "users_with_predictions": predictions_count,
        "leaderboard": leaderboard[:20],
        "recent_events": recent_events[:30],
        "trigger_match_id": trigger_match_id,
        "trigger_source": trigger_source,
    }
