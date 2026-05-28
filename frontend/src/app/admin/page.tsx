"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { admin as adminApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

export default function AdminPage() {
  const user = useAuthStore((s) => s.user);
  const router = useRouter();
  const qc = useQueryClient();
  const [recalcMsg, setRecalcMsg] = useState("");
  const [matchSaveMsg, setMatchSaveMsg] = useState("");
  const [resetMsg, setResetMsg] = useState("");

  const invalidateAllData = () => {
    qc.invalidateQueries({ queryKey: ["leaderboard"] });
    qc.invalidateQueries({ queryKey: ["scoring-events"] });
    qc.invalidateQueries({ queryKey: ["daily"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["admin-matches"] });
    qc.invalidateQueries({ queryKey: ["matches"] });
    qc.invalidateQueries({ queryKey: ["standings"] });
  };
  const [importMsg, setImportMsg] = useState("");
  const [testingMsg, setTestingMsg] = useState("");
  const [matchStageFilter, setMatchStageFilter] = useState<string>("group");

  const { data: tournaments } = useQuery({
    queryKey: ["admin-tournaments"],
    queryFn: adminApi.listTournaments,
    enabled: !!user?.is_admin,
  });

  const importTournament = useMutation({
    mutationFn: ({ slug, reset }: { slug: string; reset: boolean }) => adminApi.importTournament(slug, reset),
    onSuccess: (data) => {
      setImportMsg(`Imported ${data.teams} teams, ${data.matches} matches`);
      qc.invalidateQueries();
    },
  });

  const validateTournament = useMutation({
    mutationFn: () => adminApi.validateTournament("worldcup_2026"),
  });

  const previewBracket = useMutation({
    mutationFn: adminApi.previewBracket,
  });

  const { data: settings } = useQuery({
    queryKey: ["admin-settings"],
    queryFn: adminApi.settings,
    enabled: !!user?.is_admin,
  });

  const { data: matchAudit } = useQuery({
    queryKey: ["admin-matches-audit"],
    queryFn: adminApi.matchesAudit,
    enabled: !!user?.is_admin,
  });

  const { data: matches } = useQuery({
    queryKey: ["admin-matches", matchStageFilter],
    queryFn: () => adminApi.matches(matchStageFilter === "all" ? undefined : matchStageFilter),
    enabled: !!user?.is_admin,
  });

  const populateKnockout = useMutation({
    mutationFn: adminApi.populateKnockout,
    onSuccess: (d) => {
      setMatchSaveMsg(d.message);
      invalidateAllData();
      qc.invalidateQueries({ queryKey: ["admin-matches"] });
    },
  });

  const { data: users } = useQuery({
    queryKey: ["admin-users"],
    queryFn: adminApi.users,
    enabled: !!user?.is_admin,
  });

  const updateSettings = useMutation({
    mutationFn: adminApi.updateSettings,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] });
      invalidateAllData();
    },
  });

  const updateMatch = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => adminApi.updateMatch(id, data),
    onSuccess: (data) => {
      invalidateAllData();
      const s = data.scoring;
      if (s?.scored) {
        setMatchSaveMsg(`Scored ${s.users_scored ?? 0} users — leaderboard updated`);
      } else if (s?.reason === "incomplete_scores") {
        setMatchSaveMsg("Saved — enter both scores to trigger scoring");
      } else {
        setMatchSaveMsg("Match saved");
      }
    },
  });

  const recalculate = useMutation({
    mutationFn: adminApi.recalculate,
    onSuccess: (data) => {
      setRecalcMsg(`Recomputed ${data.users_scored} users`);
      invalidateAllData();
    },
  });

  const resetMatchResults = useMutation({
    mutationFn: adminApi.resetMatchResults,
    onSuccess: (data) => {
      setResetMsg(`${data.message} — leaderboard refreshed`);
      setMatchSaveMsg("");
      invalidateAllData();
    },
  });

  const resetPreds = useMutation({
    mutationFn: adminApi.resetPredictions,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      invalidateAllData();
    },
  });

  const fillRandom = useMutation({
    mutationFn: adminApi.fillRandomResults,
    onSuccess: (d) => { setTestingMsg(d.message); qc.invalidateQueries(); },
  });
  const simulateMatchday = useMutation({
    mutationFn: adminApi.simulateMatchday,
    onSuccess: (d) => { setTestingMsg(d.message); qc.invalidateQueries(); },
  });
  const generateDemo = useMutation({
    mutationFn: () => adminApi.generateDemoUsers(10),
    onSuccess: (d) => setTestingMsg(`${d.message} — password: ${d.password}`),
  });

  if (!user?.is_admin) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="text-pitch-300 mb-4">Admin access required.</p>
        <Link href="/login" className="btn-primary">Login</Link>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-2">Admin Dashboard</h1>
      {settings?.tournament && (
        <p className="text-pitch-300 mb-8">Active: {settings.tournament.name}</p>
      )}

      <div className="card mb-8">
        <h2 className="text-lg font-bold mb-4">Tournament Data</h2>
        <div className="flex flex-wrap gap-3 mb-4">
          <button onClick={() => validateTournament.mutate()} className="btn-secondary">
            Validate Seed Data
          </button>
          <button onClick={() => importTournament.mutate({ slug: "worldcup_2026", reset: true })} className="btn-secondary">
            Re-import World Cup 2026
          </button>
          <button onClick={() => previewBracket.mutate()} className="btn-secondary">
            Preview R32 Bracket
          </button>
        </div>
        {validateTournament.data && (
          <p className={`text-sm mb-2 ${validateTournament.data.valid ? "text-green-400" : "text-red-400"}`}>
            Validation: {validateTournament.data.valid ? "OK" : validateTournament.data.errors.join(", ")}
          </p>
        )}
        {importMsg && <p className="text-green-400 text-sm mb-2">{importMsg}</p>}
        {tournaments && (
          <ul className="text-sm text-pitch-300">
            {tournaments.map((t) => (
              <li key={t.id}>{t.name} ({t.slug}) {t.is_active && "· active"}</li>
            ))}
          </ul>
        )}
        {previewBracket.data?.r32 && previewBracket.data.r32.length > 0 && (
          <div className="mt-4 max-h-48 overflow-y-auto text-xs">
            {previewBracket.data.r32.map((m) => (
              <div key={m.label}>{m.label}: {m.team_a} vs {m.team_b}</div>
            ))}
          </div>
        )}
      </div>

      <div className="card mb-8 border-dashed border-yellow-600/40">
        <h2 className="text-lg font-bold mb-2">Testing Tools</h2>
        <p className="text-sm text-pitch-400 mb-4">Development only — disabled when ENABLE_TESTING_TOOLS=false</p>
        <div className="flex flex-wrap gap-3">
          <button onClick={() => fillRandom.mutate()} disabled={fillRandom.isPending} className="btn-secondary">
            Fill Random Results
          </button>
          <button onClick={() => simulateMatchday.mutate()} disabled={simulateMatchday.isPending} className="btn-secondary">
            Simulate Matchday
          </button>
          <button onClick={() => generateDemo.mutate()} disabled={generateDemo.isPending} className="btn-secondary">
            Generate Demo Users
          </button>
        </div>
        {testingMsg && <p className="text-green-400 text-sm mt-3">{testingMsg}</p>}
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mb-8">
        <div className="card">
          <h2 className="text-lg font-bold mb-4">Tournament Control</h2>
          <div className="space-y-3">
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings?.predictions_locked ?? false}
                onChange={(e) => updateSettings.mutate({ predictions_locked: e.target.checked })}
              />
              Lock predictions
            </label>
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings?.tournament_started ?? false}
                onChange={(e) => updateSettings.mutate({ tournament_started: e.target.checked })}
              />
              Tournament started
            </label>
            <div>
              <label className="block text-sm mb-1">Actual Top Scorer</label>
              <input
                className="input"
                defaultValue={settings?.actual_top_scorer ?? ""}
                onBlur={(e) => updateSettings.mutate({ actual_top_scorer: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-sm mb-1">Actual Top Assister</label>
              <input
                className="input"
                defaultValue={settings?.actual_top_assister ?? ""}
                onBlur={(e) => updateSettings.mutate({ actual_top_assister: e.target.value })}
              />
            </div>
            <div className="pt-4 border-t border-pitch-600">
              <button
                type="button"
                onClick={() => {
                  if (confirm("Clear ALL match results and reset scores? This cannot be undone.")) {
                    resetMatchResults.mutate();
                  }
                }}
                disabled={resetMatchResults.isPending}
                className="btn-secondary w-full text-red-300 border-red-500/40"
              >
                {resetMatchResults.isPending ? "Resetting…" : "Reset All Match Results"}
              </button>
              {resetMsg && <p className="text-green-400 text-sm mt-2">{resetMsg}</p>}
            </div>
          </div>
        </div>

        <div className="card">
          <h2 className="text-lg font-bold mb-4">Emergency Recalculation</h2>
          <p className="text-sm text-pitch-300 mb-4">
            Saving match results above automatically scores all users and refreshes the leaderboard.
            Use this only if scores look out of sync.
          </p>
          <button
            onClick={() => recalculate.mutate()}
            disabled={recalculate.isPending}
            className="btn-primary w-full"
          >
            {recalculate.isPending ? "Recalculating..." : "Recalculate All Scores"}
          </button>
          {recalcMsg && <p className="text-green-400 text-sm mt-2">{recalcMsg}</p>}
        </div>
      </div>

      <div className="card mb-8">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
          <div>
            <h2 className="text-lg font-bold">Match Results</h2>
            <p className="text-sm text-pitch-300 mt-1">
              Enter real scores and save — scoring runs automatically (no manual recalc needed).
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              if (confirm("Clear ALL match results and reset scores? This cannot be undone.")) {
                resetMatchResults.mutate();
              }
            }}
            disabled={resetMatchResults.isPending}
            className="btn-secondary text-red-300 border-red-500/40 shrink-0"
          >
            {resetMatchResults.isPending ? "Resetting…" : "Reset All Match Results"}
          </button>
        </div>
        {resetMsg && <p className="text-green-400 text-sm mb-3">{resetMsg}</p>}
        {matchSaveMsg && <p className="text-green-400 text-sm mb-3">{matchSaveMsg}</p>}
        {matchAudit && (
          <p className="text-sm text-pitch-400 mb-3">
            DB: {matchAudit.database.by_stage.group ?? 0}/72 group · {matchAudit.database.total} total
            {!matchAudit.group_complete && matchAudit.group_match_numbers.missing.length > 0 && (
              <span className="text-red-400"> · missing #{matchAudit.group_match_numbers.missing.slice(0, 5).join(", ")}…</span>
            )}
          </p>
        )}
        <div className="flex flex-wrap gap-2 mb-3">
          {["group", "R32", "R16", "QF", "SF", "F", "all"].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setMatchStageFilter(s)}
              className={`px-3 py-1 rounded text-xs ${matchStageFilter === s ? "bg-gold-500 text-pitch-900" : "bg-pitch-800"}`}
            >
              {s === "all" ? "All" : s}
            </button>
          ))}
          <button
            type="button"
            onClick={() => populateKnockout.mutate()}
            disabled={populateKnockout.isPending}
            className="btn-secondary text-xs py-1"
          >
            Generate real KO bracket
          </button>
        </div>
        <p className="text-xs text-pitch-500 mb-2">{matches?.length ?? 0} matches shown</p>
        <div className="overflow-x-auto max-h-[32rem] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-pitch-800">
              <tr className="text-pitch-300 border-b border-pitch-600">
                <th className="text-left py-2">Stage</th>
                <th className="text-left py-2">Match</th>
                <th className="py-2">Score A</th>
                <th className="py-2">Score B</th>
                <th className="py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {matches?.map((m) => (
                <MatchRow key={m.id} match={m} onSave={(data) => updateMatch.mutate({ id: m.id, data })} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2 className="text-lg font-bold mb-4">Users ({users?.length ?? 0})</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-pitch-300 border-b border-pitch-600">
              <th className="text-left py-2">Name</th>
              <th className="text-left py-2">Username</th>
              <th className="text-right py-2">Predictions</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {users?.map((u) => (
              <tr key={u.id} className="border-b border-pitch-700/50">
                <td className="py-2">{u.name}</td>
                <td className="py-2 text-pitch-300">@{u.username}</td>
                <td className="py-2 text-right">{u.prediction_count}</td>
                <td className="py-2 text-right">
                  {u.prediction_count > 0 && (
                    <button
                      onClick={() => resetPreds.mutate(u.id)}
                      className="text-xs text-red-400 hover:underline"
                    >
                      Reset
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MatchRow({
  match,
  onSave,
}: {
  match: { id: number; stage: string; team_a_name: string; team_b_name: string; real_score_a: number | null; real_score_b: number | null; bracket_slot: string | null };
  onSave: (data: Record<string, unknown>) => void;
}) {
  const [a, setA] = useState(match.real_score_a ?? "");
  const [b, setB] = useState(match.real_score_b ?? "");

  return (
    <tr className="border-b border-pitch-700/30">
      <td className="py-2 text-pitch-400">{match.stage}</td>
      <td className="py-2">
        {match.team_a_name} vs {match.team_b_name}
        {match.bracket_slot && <span className="text-xs text-pitch-500 ml-1">({match.bracket_slot})</span>}
      </td>
      <td className="py-2">
        <input type="number" min={0} className="input w-14 text-center" value={a} onChange={(e) => setA(e.target.value)} />
      </td>
      <td className="py-2">
        <input type="number" min={0} className="input w-14 text-center" value={b} onChange={(e) => setB(e.target.value)} />
      </td>
      <td className="py-2">
        <button
          onClick={() =>
            onSave({
              real_score_a: parseInt(String(a)) || 0,
              real_score_b: parseInt(String(b)) || 0,
              status: "finished",
            })
          }
          className="btn-secondary text-xs py-1"
        >
          Save
        </button>
      </td>
    </tr>
  );
}
