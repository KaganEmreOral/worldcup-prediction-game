"use client";

import { useQuery } from "@tanstack/react-query";
import { leaderboard } from "@/lib/api";

function RankChange({ change }: { change: number | null | undefined }) {
  if (change == null || change === 0) return <span className="text-pitch-500 text-xs">—</span>;
  if (change > 0) return <span className="text-green-400 text-xs font-medium">▲{change}</span>;
  return <span className="text-red-400 text-xs font-medium">▼{Math.abs(change)}</span>;
}

export default function LeaderboardPage() {
  const poll = { refetchInterval: 20_000 };
  const { data, isLoading } = useQuery({ queryKey: ["leaderboard"], queryFn: leaderboard.list, ...poll });
  const { data: events } = useQuery({ queryKey: ["scoring-events"], queryFn: leaderboard.events, ...poll });
  const { data: daily } = useQuery({ queryKey: ["daily"], queryFn: leaderboard.daily, refetchInterval: 60_000 });

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 sm:py-8">
      <h1 className="text-2xl sm:text-3xl font-bold mb-8">🏆 Leaderboard</h1>

      {isLoading ? (
        <p className="text-pitch-300">Loading...</p>
      ) : !data?.length ? (
        <div className="card text-center text-pitch-300">
          No scores yet. Predictions will be scored once match results are entered.
        </div>
      ) : (
        <div className="card overflow-x-auto p-0 sm:p-6">
          <table className="w-full text-sm standings-table">
            <thead>
              <tr className="border-b border-pitch-600 text-pitch-300">
                <th className="text-left py-3 px-2">#</th>
                <th className="text-left py-3 px-2">Move</th>
                <th className="text-left py-3 px-2">Player</th>
                <th className="text-right py-3 px-2 hidden sm:table-cell">Today</th>
                <th className="text-right py-3 px-2 hidden md:table-cell">Group</th>
                <th className="text-right py-3 px-2 hidden md:table-cell">KO</th>
                <th className="text-right py-3 px-2">Total</th>
              </tr>
            </thead>
            <tbody>
              {data.map((entry) => (
                <tr key={entry.user_id} className="border-b border-pitch-700/50 hover:bg-pitch-700/30">
                  <td className="py-3 px-2">
                    {entry.rank <= 3 ? ["🥇", "🥈", "🥉"][entry.rank - 1] : entry.rank}
                  </td>
                  <td className="py-3 px-2">
                    <RankChange change={entry.rank_change} />
                  </td>
                  <td className="py-3 px-2 font-medium">
                    <span className="block truncate max-w-[140px] sm:max-w-none">{entry.name}</span>
                    {entry.username && (
                      <span className="text-xs text-pitch-500">@{entry.username}</span>
                    )}
                  </td>
                  <td className="py-3 px-2 text-right text-pitch-300 hidden sm:table-cell">
                    {entry.daily_points != null && entry.daily_points > 0 ? (
                      <span className="text-green-400">+{entry.daily_points.toFixed(1)}</span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="py-3 px-2 text-right text-pitch-300 hidden md:table-cell">{entry.group_score}</td>
                  <td className="py-3 px-2 text-right text-pitch-300 hidden md:table-cell">{entry.knockout_score}</td>
                  <td className="py-3 px-2 text-right font-bold text-gold-400">{entry.total_score.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {events && events.length > 0 && (
        <div className="mt-10">
          <h2 className="text-xl font-bold mb-4">Latest Scoring Events</h2>
          <div className="space-y-2">
            {events.slice(0, 12).map((e, i) => (
              <div key={i} className="card card-compact flex flex-wrap items-center justify-between gap-2 text-sm">
                <div>
                  <span className="font-medium">{e.user_name}</span>
                  <span className="text-pitch-400 ml-2">
                    {e.team_a_code && e.team_b_code ? `${e.team_a_code} vs ${e.team_b_code}` : ""}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {e.label && <span className="text-xs text-pitch-400">{e.label}</span>}
                  <span className="font-bold text-gold-400">+{e.points}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {daily && daily.length > 0 && (
        <div className="mt-12">
          <h2 className="text-xl font-bold mb-4">Daily History</h2>
          <div className="space-y-4">
            {daily.slice(0, 7).map((snap) => (
              <div key={snap.date} className="card card-compact">
                <h3 className="text-sm text-pitch-300 mb-2">{new Date(snap.date).toLocaleString()}</h3>
                <div className="flex flex-wrap gap-2">
                  {snap.rankings.slice(0, 5).map((r: { name: string; total_score: number }, i: number) => (
                    <span key={i} className="text-sm bg-pitch-700 px-2 py-1 rounded">
                      {i + 1}. {r.name} ({r.total_score.toFixed(1)})
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
