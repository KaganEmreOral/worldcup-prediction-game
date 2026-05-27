"use client";

import { flagUrl } from "@/lib/format";

export function TeamBadge({
  code,
  name,
  flag,
  align = "left",
}: {
  code: string;
  name?: string;
  flag?: string | null;
  align?: "left" | "right";
}) {
  const url = flagUrl(flag || undefined, 40);
  return (
    <div className={`flex items-center gap-2 ${align === "right" ? "flex-row-reverse text-right" : ""}`}>
      {url && <img src={url} alt="" className="w-6 h-4 object-cover rounded-sm" loading="lazy" />}
      <div>
        <span className="font-bold">{code}</span>
        {name && <span className="text-pitch-400 text-xs ml-1 hidden sm:inline">{name}</span>}
      </div>
    </div>
  );
}
