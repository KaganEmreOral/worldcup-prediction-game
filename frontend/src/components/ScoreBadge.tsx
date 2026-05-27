"use client";

export function ScoreBadge({
  scoring,
}: {
  scoring?: {
    points: number;
    status: "exact" | "outcome" | "wrong";
    reasons?: { label: string; points: number }[];
  } | null;
}) {
  if (!scoring || scoring.points === 0) {
    if (scoring?.status === "wrong") {
      return (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-300">
          ✗ 0 pts
        </span>
      );
    }
    return null;
  }

  const styles = {
    exact: "bg-gold-500/25 text-gold-300 border-gold-500/40",
    outcome: "bg-pitch-500/30 text-pitch-200 border-pitch-500/40",
    wrong: "bg-red-500/20 text-red-300 border-red-500/40",
  };
  const icons = { exact: "🎯", outcome: "✓", wrong: "✗" };
  const labels = { exact: "Exact", outcome: "Outcome", wrong: "Miss" };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border font-medium ${styles[scoring.status]}`}>
        {icons[scoring.status]} {labels[scoring.status]} +{scoring.points}
      </span>
      {scoring.reasons?.map((r, i) => (
        <span key={i} className="text-[10px] text-pitch-400 hidden sm:inline">{r.label}</span>
      ))}
    </div>
  );
}
