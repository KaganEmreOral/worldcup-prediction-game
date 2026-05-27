"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { dashboard, tournament as tournamentApi } from "@/lib/api";
import { MatchBriefCard } from "@/components/MatchBriefCard";
import { flagUrl } from "@/lib/format";

type StandingRow = {
  team_code: string;
  team_name?: string;
  points: number;
  goal_difference: number;
  goals_for: number;
};

export default function HomePage() {
  const { data: activeTournament } = useQuery({ queryKey: ["tournament"], queryFn: tournamentApi.active });
  const { data, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: dashboard.get, refetchInterval: 60000 });

  const groupNames = data?.standings ? Object.keys(data.standings).sort() : [];

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 sm:py-8">
      <header className="mb-8">
        <h1 className="text-3xl sm:text-4xl font-bold mb-2 bg-gradient-to-r from-gold-400 to-pitch-400 bg-clip-text text-transparent">
          {activeTournament?.name || "World Cup 2026"} Live
        </h1>
        <p className="text-pitch-300">
          Tournament dashboard — standings, results, fixtures & leaderboard
        </p>
      </header>

      {isLoading ? (
        <p className="text-pitch-400">Loading tournament data...</p>
      ) : (
        <>
          {/* Stats row */}
          {data?.stats && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
              {[
                { label: "Predictions", value: data.stats.total_predictions },
                { label: "Players", value: data.stats.users_with_predictions },
                { label: "Finished", value: `${data.stats.finished_matches}/${data.stats.total_matches}` },
                {
                  label: "Top pick (🏆)",
                  value: data.stats.most_predicted_champion || "—",
                  sub: data.stats.champion_pick_count ? `${data.stats.champion_pick_count} picks` : undefined,
                },
                {
                  label: "Golden Boot pick",
                  value: data.stats.most_predicted_scorer || "—",
                  sub: data.stats.scorer_pick_count ? `${data.stats.scorer_pick_count} picks` : undefined,
                },
              ].map((s) => (
                <div key={s.label} className="card card-compact text-center">
                  <p className="text-[10px] sm:text-xs text-pitch-400 uppercase tracking-wide">{s.label}</p>
                  <p className="text-sm sm:text-lg font-bold truncate">{s.value}</p>
                  {s.sub && <p className="text-[10px] text-pitch-500">{s.sub}</p>}
                </div>
              ))}
              <div className="card card-compact flex flex-col items-center justify-center gap-2 col-span-2 sm:col-span-1">
                <Link href="/predict" className="btn-primary text-sm w-full text-center">Predict</Link>
                <Link href="/register" className="btn-secondary text-sm w-full text-center">Join</Link>
              </div>
            </div>
          )}

          <div className="grid lg:grid-cols-3 gap-6 mb-8">
            {/* Latest results */}
            <section className="lg:col-span-1">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-bold">Latest Results</h2>
                <Link href="/matches" className="text-xs text-gold-400 hover:underline">All matches</Link>
              </div>
              <div className="space-y-2">
                {data?.latest_results?.length ? (
                  data.latest_results.map((m) => <MatchBriefCard key={m.id} m={m} compact />)
                ) : (
                  <div className="card card-compact text-pitch-400 text-sm">No results yet</div>
                )}
              </div>
            </section>

            {/* Upcoming */}
            <section className="lg:col-span-1">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-bold">Upcoming Fixtures</h2>
              </div>
              <div className="space-y-2">
                {data?.upcoming_fixtures?.length ? (
                  data.upcoming_fixtures.map((m) => <MatchBriefCard key={m.id} m={m} compact />)
                ) : (
                  <div className="card card-compact text-pitch-400 text-sm">No upcoming fixtures</div>
                )}
              </div>
            </section>

            {/* Leaderboard */}
            <section className="lg:col-span-1">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-bold">Top Leaderboard</h2>
                <Link href="/leaderboard" className="text-xs text-gold-400 hover:underline">Full board</Link>
              </div>
              <div className="card overflow-hidden p-0">
                <table className="w-full text-sm standings-table">
                  <thead>
                    <tr className="text-pitch-400 border-b border-pitch-700">
                      <th className="py-2 px-3 text-left">#</th>
                      <th className="py-2 px-3 text-left">Player</th>
                      <th className="py-2 px-3 text-right">Pts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.leaderboard?.length ? (
                      data.leaderboard.map((e) => (
                        <tr key={e.rank} className="border-b border-pitch-700/40 hover:bg-pitch-700/20">
                          <td className="py-2 px-3">{e.rank <= 3 ? ["🥇", "🥈", "🥉"][e.rank - 1] : e.rank}</td>
                          <td className="py-2 px-3 font-medium truncate max-w-[120px]">{e.name}</td>
                          <td className="py-2 px-3 text-right font-bold text-gold-400">{e.total_score.toFixed(1)}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={3} className="py-4 px-3 text-center text-pitch-400">No scores yet</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          {/* Group standings */}
          <section>
            <h2 className="text-xl font-bold mb-4">Group Standings</h2>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {groupNames.map((g) => {
                const rows = (data!.standings[g] as StandingRow[]) || [];
                return (
                  <div key={g} className="card card-compact p-4">
                    <h3 className="font-bold mb-2 text-gold-400">Group {g}</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs standings-table">
                        <thead>
                          <tr className="text-pitch-400">
                            <th className="text-left py-1">Team</th>
                            <th className="text-center py-1">Pts</th>
                            <th className="text-center py-1">GD</th>
                            <th className="text-center py-1">GF</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((t, i) => (
                            <tr key={t.team_code} className={i < 2 ? "text-pitch-100" : i === 2 ? "text-yellow-400/90" : "text-pitch-400"}>
                              <td className="py-1">
                                <span className="inline-flex items-center gap-1">
                                  {data?.team_flags?.[t.team_code] && (
                                    <img src={flagUrl(data.team_flags[t.team_code], 16) || ""} alt="" className="w-4 h-3 object-cover rounded-sm" />
                                  )}
                                  {t.team_code}
                                </span>
                              </td>
                              <td className="text-center py-1 font-medium">{t.points}</td>
                              <td className="text-center py-1">{t.goal_difference > 0 ? `+${t.goal_difference}` : t.goal_difference}</td>
                              <td className="text-center py-1">{t.goals_for}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
