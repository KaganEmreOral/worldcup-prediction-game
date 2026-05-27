"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useAuthStore } from "@/lib/store";
import { leaderboard, predictions } from "@/lib/api";

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const { data: score } = useQuery({
    queryKey: ["my-score"],
    queryFn: leaderboard.me,
    enabled: !!user,
  });
  const { data: status } = useQuery({
    queryKey: ["pred-status"],
    queryFn: predictions.status,
    enabled: !!user,
  });
  const { data: standings } = useQuery({
    queryKey: ["my-standings"],
    queryFn: leaderboard.standings,
    enabled: !!user && !!status?.submitted,
  });

  if (!user) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="mb-4 text-pitch-300">Please login to view your dashboard.</p>
        <Link href="/login" className="btn-primary">Login</Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 sm:py-8">
      <h1 className="text-2xl sm:text-3xl font-bold mb-2">Welcome, @{user.username}</h1>
      <p className="text-pitch-300 mb-8">Your tournament prediction dashboard</p>

      {!status?.submitted ? (
        <div className="card text-center mb-8">
          <p className="mb-4">You haven&apos;t submitted predictions yet.</p>
          <Link href="/predict" className="btn-primary">Submit Predictions</Link>
        </div>
      ) : (
        <p className="text-pitch-400 text-sm mb-6">✓ Predictions submitted {status.locked ? "(locked)" : ""}</p>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-8">
        {[
          { label: "Group Score", value: (score?.group_score ?? 0) + (score?.qualification_score ?? 0) },
          { label: "Knockout Score", value: score?.knockout_score ?? 0 },
          { label: "Special Score", value: score?.special_score ?? 0 },
          { label: "Total Score", value: score?.total_score ?? 0, highlight: true },
        ].map((s) => (
          <div key={s.label} className="card card-compact text-center">
            <p className="text-xs sm:text-sm text-pitch-300 mb-1">{s.label}</p>
            <p className={`text-2xl sm:text-3xl font-bold ${s.highlight ? "text-gold-400" : ""}`}>
              {typeof s.value === "number" ? s.value.toFixed(1) : s.value}
            </p>
            {s.label === "Total Score" && score?.chain_bonus ? (
              <p className="text-xs text-pitch-400 mt-1">+{score.chain_bonus.toFixed(1)} chain bonus</p>
            ) : null}
          </div>
        ))}
      </div>

      <div className="mb-8">
        <Link href="/scores" className="btn-primary">View Detailed Score Breakdown →</Link>
      </div>

      {score?.breakdown_json && (
        <div className="card mb-8">
          <h2 className="text-lg font-bold mb-3">Score Summary</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            {Object.entries(score.breakdown_json)
              .filter(([k]) => k !== "details" && k !== "match_scores")
              .map(([k, v]) => (
                <div key={k} className="bg-pitch-900/50 rounded-lg p-3">
                  <p className="text-pitch-400 capitalize text-xs">{k.replace(/_/g, " ")}</p>
                  <p className="font-bold">{String(v)}</p>
                </div>
              ))}
          </div>
        </div>
      )}

      {standings && standings.length > 0 && (
        <div>
          <h2 className="text-xl font-bold mb-4">Your Simulated Standings</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {standings.map((g) => (
              <div key={g.group_name} className="card card-compact">
                <h3 className="font-bold mb-2 text-gold-400">Group {g.group_name}</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs standings-table">
                    <thead>
                      <tr className="text-pitch-400">
                        <th className="text-left">Team</th>
                        <th>Pts</th>
                        <th>GD</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(g.standings as { team_code: string; points: number; goal_difference: number }[]).map((t, i) => (
                        <tr key={i} className={i < 2 ? "text-pitch-100" : i === 2 ? "text-yellow-400/80" : "text-pitch-400"}>
                          <td>{t.team_code}</td>
                          <td className="text-center">{t.points}</td>
                          <td className="text-center">{t.goal_difference}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
