"use client";

import { TeamBadge } from "@/components/TeamBadge";
import { ScoreBadge } from "@/components/ScoreBadge";
import { formatKickoff } from "@/lib/format";
import type { Match } from "@/lib/api";

type BriefMatch = Pick<
  Match,
  | "id"
  | "match_number"
  | "stage"
  | "group_name"
  | "team_a_code"
  | "team_b_code"
  | "team_a_name"
  | "team_b_name"
  | "team_a_flag"
  | "team_b_flag"
  | "real_score_a"
  | "real_score_b"
  | "status"
  | "kickoff_time_utc"
  | "stadium"
  | "prediction"
  | "scoring"
>;

export function MatchBriefCard({ m, compact }: { m: BriefMatch; compact?: boolean }) {
  const codeA = m.team_a_code || "TBD";
  const codeB = m.team_b_code || "TBD";

  return (
    <div className="card card-compact">
      <div className="flex items-center justify-between gap-2 mb-2 text-xs text-pitch-400">
        <span>
          {m.match_number ? `#${m.match_number}` : ""}
          {m.group_name ? ` · Group ${m.group_name}` : m.stage !== "group" ? ` · ${m.stage}` : ""}
        </span>
        <span>{formatKickoff(m.kickoff_time_utc)}</span>
      </div>
      <div className="flex items-center justify-between gap-2 sm:gap-4">
        <TeamBadge code={codeA} name={m.team_a_name} flag={m.team_a_flag} />
        <div className="text-center min-w-[64px] shrink-0">
          {m.real_score_a != null && m.real_score_b != null ? (
            <span className="text-lg sm:text-xl font-bold">
              {m.real_score_a} - {m.real_score_b}
            </span>
          ) : (
            <span className="text-pitch-400 text-xs uppercase">{m.status || "scheduled"}</span>
          )}
        </div>
        <TeamBadge code={codeB} name={m.team_b_name} flag={m.team_b_flag} align="right" />
      </div>
      {!compact && m.stadium && (
        <p className="text-xs text-pitch-500 mt-2 text-center truncate">
          {m.stadium.name}, {m.stadium.city}
        </p>
      )}
      {(m.prediction || m.scoring) && (
        <div className="mt-2 flex flex-col sm:flex-row items-center justify-center gap-2">
          {m.prediction && (
            <p className="text-xs text-gold-400/80">
              Your pick: {m.prediction.score_a}-{m.prediction.score_b}
            </p>
          )}
          {m.scoring && <ScoreBadge scoring={m.scoring} />}
        </div>
      )}
    </div>
  );
}
