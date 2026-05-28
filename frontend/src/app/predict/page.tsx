"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import { useState, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { matches as matchesApi, predictions as predApi, simulation, tournament as tournamentApi, type BracketMatch, type Match } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { TeamBadge } from "@/components/TeamBadge";
import { formatKickoff } from "@/lib/format";

const STAGES = ["group", "knockout", "special"] as const;
type Tab = (typeof STAGES)[number];

export default function PredictPage() {
  const user = useAuthStore((s) => s.user);
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("group");
  const [activeGroup, setActiveGroup] = useState("A");
  const [scores, setScores] = useState<Record<number, [number, number]>>({});
  const [koScores, setKoScores] = useState<Record<string, [number, number]>>({});
  const [topScorer, setTopScorer] = useState("");
  const [topAssister, setTopAssister] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [previewBracket, setPreviewBracket] = useState<{ r32: BracketMatch[]; bracket: Record<string, BracketMatch[]> } | null>(null);

  const { data: activeTournament } = useQuery({ queryKey: ["tournament"], queryFn: tournamentApi.active });
  const { data: groups } = useQuery({ queryKey: ["groups"], queryFn: tournamentApi.groups });
  const { data: allMatches } = useQuery({
    queryKey: ["all-group-matches"],
    queryFn: () => matchesApi.list("group"),
    enabled: !!user,
  });
  const { data: status } = useQuery({ queryKey: ["pred-status"], queryFn: predApi.status, enabled: !!user });

  const groupNames = groups?.map((g) => g.name) || [];
  const groupMatches = useMemo(
    () => (allMatches || []).filter((m) => m.group_name === activeGroup).sort((a, b) => (a.match_number || 0) - (b.match_number || 0)),
    [allMatches, activeGroup]
  );

  const totalGroupMatches = allMatches?.length || 72;
  const filledCount = Object.keys(scores).length;
  const allGroupsComplete = groupNames.every((g) =>
    (allMatches || []).filter((m) => m.group_name === g).every((m) => scores[m.id] !== undefined)
  );

  const expectedKoLabels = useMemo(() => {
    const labels = new Set<string>();
    if (previewBracket?.bracket) {
      for (const list of Object.values(previewBracket.bracket)) {
        for (const m of list) labels.add(m.label);
      }
    }
    if (previewBracket?.r32) {
      for (const m of previewBracket.r32) labels.add(m.label);
    }
    return labels;
  }, [previewBracket]);

  const koLabels = Array.from(expectedKoLabels);
  const knockoutFilled = koLabels.length > 0 && koLabels.every((l) => koScores[l] !== undefined);
  const knockoutNoDraws = koLabels.every((l) => {
    const s = koScores[l];
    return s && s[0] !== s[1];
  });
  const specialComplete = topScorer.trim().length > 0 && topAssister.trim().length > 0;
  const canSubmit = allGroupsComplete && knockoutFilled && knockoutNoDraws && specialComplete;

  const previewMutation = useMutation({
    mutationFn: (preds: { match_id: number; predicted_score_a: number; predicted_score_b: number }[]) =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"}/simulation/preview-bracket`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify({
          predictions: preds,
          knockout_predictions: Object.entries(koScores).map(([bracket_slot, [predicted_score_a, predicted_score_b]]) => ({
            bracket_slot,
            predicted_score_a,
            predicted_score_b,
          })),
        }),
      }).then((r) => r.json()),
  });

  useEffect(() => {
    if (tab === "knockout" && allGroupsComplete && filledCount > 0) {
      const preds = Object.entries(scores).map(([id, [a, b]]) => ({
        match_id: Number(id),
        predicted_score_a: a,
        predicted_score_b: b,
      }));
      previewMutation.mutate(preds, {
        onSuccess: (data) => setPreviewBracket({ r32: data.r32 || [], bracket: data.bracket || {} }),
      });
    }
  }, [tab, allGroupsComplete, filledCount]); // eslint-disable-line react-hooks/exhaustive-deps

  function setScore(matchId: number, side: "a" | "b", val: number) {
    setScores((prev) => {
      const cur = prev[matchId] || [0, 0];
      return { ...prev, [matchId]: side === "a" ? [val, cur[1]] : [cur[0], val] };
    });
  }

  function setKoScore(label: string, side: "a" | "b", val: number) {
    setKoScores((prev) => {
      const cur = prev[label] || [0, 0];
      const score: [number, number] = side === "a" ? [val, cur[1]] : [cur[0], val];
      return { ...prev, [label]: score };
    });
  }

  async function handleSubmit() {
    setError("");
    setSubmitting(true);
    try {
      const groupPreds = Object.entries(scores).map(([id, [a, b]]) => ({
        match_id: Number(id),
        predicted_score_a: a,
        predicted_score_b: b,
      }));

      const findBracketMatch = (slot: string) => {
        const r32m = previewBracket?.r32?.find((m) => m.label === slot);
        if (r32m) return r32m;
        for (const list of Object.values(previewBracket?.bracket || {})) {
          const found = list.find((m) => m.label === slot);
          if (found) return found;
        }
        return null;
      };

      const knockoutPreds = Object.entries(koScores).map(([slot, [a, b]]) => {
        const bm = findBracketMatch(slot);
        const stage = slot.startsWith("R32") ? "R32" : slot.startsWith("R16") ? "R16" : slot.startsWith("QF") ? "QF" : slot.startsWith("SF") ? "SF" : "F";
        return {
          bracket_slot: slot,
          stage,
          sim_team_a_id: bm?.team_a?.id,
          sim_team_b_id: bm?.team_b?.id,
          predicted_score_a: a,
          predicted_score_b: b,
        };
      });

      await predApi.submit({
        predictions: groupPreds,
        knockout_predictions: knockoutPreds,
        top_scorer: topScorer || null,
        top_assister: topAssister || null,
      });
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (!user) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <Link href="/login" className="btn-primary">Login to predict</Link>
      </div>
    );
  }

  if (status?.submitted) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center card">
        <p className="mb-4">Predictions already submitted.</p>
        <Link href="/dashboard" className="btn-primary">View Dashboard</Link>
      </div>
    );
  }

  if (status?.locked) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center card">
        <p>Predictions are locked. The tournament has started.</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-1">Submit Predictions</h1>
      {activeTournament && (
        <p className="text-pitch-300 mb-6">{activeTournament.name} — one submission only</p>
      )}

      <div className="flex flex-wrap gap-3 mb-4 text-sm">
        <span className={allGroupsComplete ? "text-green-400" : "text-pitch-400"}>
          {allGroupsComplete ? "✓" : "○"} Group Stage ({filledCount}/{totalGroupMatches})
        </span>
        <span className={knockoutFilled && knockoutNoDraws ? "text-green-400" : "text-pitch-400"}>
          {knockoutFilled && knockoutNoDraws ? "✓" : "○"} Knockout
        </span>
        <span className={specialComplete ? "text-green-400" : "text-pitch-400"}>
          {specialComplete ? "✓" : "○"} Special Picks
        </span>
      </div>

      <div className="flex gap-2 mb-6">
        {STAGES.map((s) => (
          <button
            key={s}
            onClick={() => setTab(s)}
            className={`px-4 py-2 rounded-lg capitalize ${tab === s ? "bg-pitch-500" : "bg-pitch-800"}`}
          >
            {s}
          </button>
        ))}
      </div>

      {tab === "group" && (
        <>
          <div className="flex flex-wrap gap-1 mb-4">
            {groupNames.map((g) => (
              <button
                key={g}
                onClick={() => setActiveGroup(g)}
                className={`w-9 h-9 rounded-lg text-sm font-bold ${activeGroup === g ? "bg-gold-500 text-pitch-900" : "bg-pitch-800"}`}
              >
                {g}
              </button>
            ))}
          </div>
          <p className="text-sm text-pitch-400 mb-4">{filledCount}/{totalGroupMatches} matches · {groupNames.filter(g => (allMatches||[]).filter(m=>m.group_name===g).every(m=>scores[m.id]!==undefined)).length}/{groupNames.length} groups complete</p>
          <div className="space-y-3">
            {groupMatches.map((m: Match) => (
              <div key={m.id} className="card">
                <div className="flex justify-between text-xs text-pitch-500 mb-2">
                  <span>#{m.match_number} · MD{m.matchday}</span>
                  <span>{formatKickoff(m.kickoff_time_utc)}</span>
                </div>
                <div className="flex items-center gap-2 sm:gap-3 prediction-row">
                  <div className="flex-1 min-w-0"><TeamBadge code={m.team_a_code} flag={m.team_a_flag} align="right" /></div>
                  <input type="number" min={0} max={20} className="input-score" value={scores[m.id]?.[0] ?? ""} onChange={(e) => setScore(m.id, "a", parseInt(e.target.value) || 0)} />
                  <span className="text-pitch-400">-</span>
                  <input type="number" min={0} max={20} className="input-score" value={scores[m.id]?.[1] ?? ""} onChange={(e) => setScore(m.id, "b", parseInt(e.target.value) || 0)} />
                  <div className="flex-1 min-w-0"><TeamBadge code={m.team_b_code} flag={m.team_b_flag} /></div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === "knockout" && (
        <div>
          {!allGroupsComplete ? (
            <p className="text-pitch-300 card">Complete all group stage predictions first to generate your knockout bracket.</p>
          ) : previewMutation.isPending ? (
            <p className="text-pitch-300">Generating bracket from your predictions...</p>
          ) : (
            <>
              <p className="text-sm text-pitch-400 mb-4">Official FIFA R32 bracket based on your simulated group results.</p>
              {(["R32", "R16", "QF", "SF", "F"] as const).map((stage) => {
                const stageMatches = previewBracket?.bracket?.[stage] || (stage === "R32" ? previewBracket?.r32 : []) || [];
                if (!stageMatches.length) return null;
                return (
                  <div key={stage} className="mb-8">
                    <h3 className="font-bold mb-2 text-gold-400">{stage === "R32" ? "Round of 32" : stage === "R16" ? "Round of 16" : stage === "QF" ? "Quarter-finals" : stage === "SF" ? "Semi-finals" : "Final"}</h3>
                    <div className="space-y-3">
                      {stageMatches.map((m) => (
                        <div key={m.label} className="card knockout-row">
                          <span className="text-pitch-500 w-full sm:w-14 shrink-0">{m.label}</span>
                          <span className="flex-1 text-right truncate">{m.team_a?.code || m.team_a?.name || "—"}</span>
                          <input type="number" min={0} className="input-score" value={koScores[m.label]?.[0] ?? ""} onChange={(e) => setKoScore(m.label, "a", parseInt(e.target.value) || 0)} />
                          <span className="text-pitch-400">-</span>
                          <input type="number" min={0} className="input-score" value={koScores[m.label]?.[1] ?? ""} onChange={(e) => setKoScore(m.label, "b", parseInt(e.target.value) || 0)} />
                          <span className="flex-1 truncate">{m.team_b?.code || m.team_b?.name || "—"}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}

      {tab === "special" && (
        <div className="card space-y-4 max-w-md">
          <div>
            <label className="block text-sm mb-1">Golden Boot (Top Scorer)</label>
            <input className="input" value={topScorer} onChange={(e) => setTopScorer(e.target.value)} placeholder="Player name" />
          </div>
          <div>
            <label className="block text-sm mb-1">Top Assist Provider</label>
            <input className="input" value={topAssister} onChange={(e) => setTopAssister(e.target.value)} placeholder="Player name" />
          </div>
        </div>
      )}

      {error && <p className="text-red-400 mt-4">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={submitting || !canSubmit}
        className="btn-primary mt-8 w-full sm:w-auto px-12 disabled:opacity-50"
      >
        {submitting ? "Submitting..." : canSubmit ? "Submit All Predictions" : "Complete all sections to submit"}
      </button>
    </div>
  );
}
