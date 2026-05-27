"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { leaderboard } from "@/lib/api";
import { ScoreBadge } from "@/components/ScoreBadge";
import { useAuthStore } from "@/lib/store";

export default function ScoresBreakdownPage() {
  const user = useAuthStore((s) => s.user);
  const { data, isLoading } = useQuery({
    queryKey: ["score-breakdown"],
    queryFn: leaderboard.breakdown,
    enabled: !!user,
  });

  if (!user) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="mb-4 text-pitch-300">Login to view your score breakdown.</p>
        <Link href="/login" className="btn-primary">Login</Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-2">Score Breakdown</h1>
      <p className="text-pitch-300 mb-8">See exactly why you earned each point</p>

      {isLoading ? (
        <p className="text-pitch-400">Loading...</p>
      ) : !data?.match_scores?.length && !data?.other?.length ? (
        <div className="card text-center text-pitch-300">
          No scoring data yet. Points appear once match results are entered and scores recalculated.
        </div>
      ) : (
        <>
          {data.summary && Object.keys(data.summary).length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
              {Object.entries(data.summary)
                .filter(([k]) => typeof data.summary[k] === "number")
                .map(([k, v]) => (
                  <div key={k} className="card card-compact text-center">
                    <p className="text-xs text-pitch-400 capitalize">{k.replace(/_/g, " ")}</p>
                    <p className="text-2xl font-bold text-gold-400">{Number(v)}</p>
                  </div>
                ))}
            </div>
          )}

          {data.other && data.other.length > 0 && (
            <section className="mb-8">
              <h2 className="text-lg font-bold mb-3">Qualification & Special</h2>
              <div className="space-y-2">
                {data.other.map((item, i) => (
                  <div key={i} className="card card-compact flex items-center justify-between gap-4">
                    <span className="text-sm">{item.label || "Bonus"}</span>
                    <span className="font-bold text-gold-400">+{item.points}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {data.match_scores && data.match_scores.length > 0 && (
            <section>
              <h2 className="text-lg font-bold mb-3">Per-Match Scoring</h2>
              <div className="space-y-2">
                {data.match_scores.map((m, i) => (
                  <div key={i} className="card card-compact">
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                      <div>
                        <span className="text-xs text-pitch-400">
                          {m.stage && m.stage !== "group" ? m.stage : m.group_name ? `Group ${m.group_name}` : ""}
                          {m.match_number ? ` · #${m.match_number}` : ""}
                        </span>
                        <p className="font-medium">
                          {m.team_a_code || "?"} vs {m.team_b_code || "?"}
                        </p>
                      </div>
                      <ScoreBadge scoring={m} />
                    </div>
                    <div className="flex flex-wrap gap-4 text-xs text-pitch-400">
                      <span>Predicted: <strong className="text-pitch-200">{m.predicted}</strong></span>
                      <span>Result: <strong className="text-pitch-200">{m.actual}</strong></span>
                    </div>
                    {m.reasons && m.reasons.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {m.reasons.map((r, j) => (
                          <span key={j} className="text-xs bg-pitch-700/60 px-2 py-0.5 rounded-full">
                            {r.label} (+{r.points})
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
