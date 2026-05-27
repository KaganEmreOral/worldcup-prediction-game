"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { matches as matchesApi, tournament as tournamentApi } from "@/lib/api";
import { MatchBriefCard } from "@/components/MatchBriefCard";

const STAGES = ["group", "R32", "R16", "QF", "SF", "F"];

export default function MatchesPage() {
  const [stage, setStage] = useState("group");
  const [group, setGroup] = useState("A");
  const [matchday, setMatchday] = useState<number | null>(null);

  const { data: activeTournament } = useQuery({ queryKey: ["tournament"], queryFn: tournamentApi.active });
  const { data: groups } = useQuery({ queryKey: ["groups"], queryFn: tournamentApi.groups });

  const { data, isLoading } = useQuery({
    queryKey: ["matches", stage, stage === "group" ? group : "", matchday],
    queryFn: () => matchesApi.list(stage, stage === "group" ? group : undefined, matchday || undefined),
  });

  const groupNames = groups?.map((g) => g.name) || [];

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 sm:py-8">
      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold">Match Results</h1>
        {activeTournament && (
          <p className="text-pitch-300 mt-1">
            {activeTournament.name} ({activeTournament.year})
          </p>
        )}
      </div>

      <div className="flex flex-wrap gap-2 mb-4 overflow-x-auto pb-1">
        {STAGES.map((s) => (
          <button
            key={s}
            onClick={() => { setStage(s); setMatchday(null); }}
            className={`px-3 py-1.5 rounded-lg text-sm whitespace-nowrap ${stage === s ? "bg-pitch-500" : "bg-pitch-800 hover:bg-pitch-700"}`}
          >
            {s === "group" ? "Group Stage" : s}
          </button>
        ))}
      </div>

      {stage === "group" && (
        <>
          <div className="flex flex-wrap gap-1 mb-3">
            {groupNames.map((g) => (
              <button
                key={g}
                onClick={() => setGroup(g)}
                className={`w-9 h-9 rounded-lg text-sm font-bold ${group === g ? "bg-gold-500 text-pitch-900" : "bg-pitch-800"}`}
              >
                {g}
              </button>
            ))}
          </div>
          <div className="flex gap-2 mb-6">
            {[1, 2, 3].map((md) => (
              <button
                key={md}
                onClick={() => setMatchday(matchday === md ? null : md)}
                className={`px-3 py-1 rounded text-sm ${matchday === md ? "bg-pitch-600" : "bg-pitch-800"}`}
              >
                MD{md}
              </button>
            ))}
          </div>
        </>
      )}

      {isLoading ? (
        <p className="text-pitch-300">Loading matches...</p>
      ) : (
        <div className="space-y-3">
          {data?.map((m) => (
            <MatchBriefCard key={m.id} m={m} />
          ))}
        </div>
      )}
    </div>
  );
}
