"""Full recalculation pipeline for all users."""

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
    UserScore,
)
from app.services.cache import invalidate
from app.services.group_simulation import MatchResult, compute_group_standings
from app.services.scoring_engine import (
    ScoreBreakdown,
    build_match_score_entry,
    compute_chain_bonus,
    score_group_match,
    score_knockout_match,
    score_qualification,
    simulate_real_groups,
    simulate_user_groups,
    _enrich_detail,
)


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


async def recalculate_all(db: AsyncSession) -> dict:
    from app.seeds.tournament_loader import get_active_tournament

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

    leaderboard = []
    recent_events: list[dict] = []

    await db.execute(delete(GroupStandingsCache))
    await db.execute(delete(KnockoutBracketCache))

    for user in users:
        pred_result = await db.execute(select(Prediction).where(Prediction.user_id == user.id))
        predictions = {p.match_id: (p.predicted_score_a, p.predicted_score_b) for p in pred_result.scalars()}

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
        user_ko_preds = {kp.bracket_slot: kp for kp in ko_pred_result.scalars()}
        real_ko_by_slot = {m.bracket_slot: m for m in knockout_matches if m.bracket_slot}

        knockout_paths: dict[int, list[bool]] = {}
        for slot, m in real_ko_by_slot.items():
            kp = user_ko_preds.get(slot)
            if not kp or m.real_score_a is None:
                continue
            wp, ep, det = score_knockout_match(
                m.stage, kp.predicted_score_a, kp.predicted_score_b, m.real_score_a, m.real_score_b
            )
            total_ko = wp + ep
            breakdown.knockout_winner_points += wp
            breakdown.knockout_exact_points += ep
            breakdown.details.extend(det)
            entry = build_match_score_entry(
                m, kp.predicted_score_a, kp.predicted_score_b, m.real_score_a, m.real_score_b,
                total_ko, det, bracket_slot=slot,
            )
            breakdown.match_scores.append(entry)
            if total_ko > 0:
                recent_events.append({**entry, "user_name": user.name, "user_id": user.id})

            real_winner = m.team_a_id if m.real_score_a > m.real_score_b else m.team_b_id
            if m.real_score_a == m.real_score_b:
                real_winner = m.team_a_id
            pred_winner = kp.sim_team_a_id if kp.predicted_score_a > kp.predicted_score_b else kp.sim_team_b_id
            if kp.predicted_score_a == kp.predicted_score_b:
                pred_winner = kp.sim_team_a_id
            correct = real_winner == pred_winner
            if kp.sim_team_a_id:
                knockout_paths.setdefault(kp.sim_team_a_id, []).append(correct and pred_winner == kp.sim_team_a_id)

        chain_bonus, chain_det = compute_chain_bonus(knockout_paths)
        breakdown.chain_bonus_points = chain_bonus
        breakdown.details.extend(chain_det)

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
        user_score.chain_bonus = breakdown.chain_bonus_points
        user_score.total_score = breakdown.total
        user_score.breakdown_json = {
            "group_match": breakdown.group_match_points,
            "qualification": breakdown.qualification_points,
            "group_winner": breakdown.group_winner_points,
            "full_group_bonus": breakdown.full_group_bonus,
            "knockout_winner": breakdown.knockout_winner_points,
            "knockout_exact": breakdown.knockout_exact_points,
            "special": breakdown.special_points,
            "chain_bonus": breakdown.chain_bonus_points,
            "details": [_enrich_detail(d) if "label" not in d else d for d in breakdown.details[:200]],
            "match_scores": breakdown.match_scores,
        }
        user_score.updated_at = datetime.now(timezone.utc)

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
    return {
        "users_scored": len(users),
        "leaderboard": leaderboard[:20],
        "recent_events": recent_events[:30],
    }
