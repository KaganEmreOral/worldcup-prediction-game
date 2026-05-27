export function flagUrl(flagCode: string | null | undefined, size: number = 24): string | null {
  if (!flagCode) return null;
  return `https://flagcdn.com/w${size}/${flagCode}.png`;
}

export function formatKickoff(utc: string | null | undefined): string {
  if (!utc) return "TBD";
  const d = new Date(utc);
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

export function formatKickoffDate(utc: string | null | undefined): string {
  if (!utc) return "";
  return new Date(utc).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
