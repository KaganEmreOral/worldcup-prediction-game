const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export interface User {
  id: number;
  username: string;
  name: string;
  is_admin: boolean;
}

export interface Match {
  id: number;
  stage: string;
  group_name: string | null;
  team_a_name: string;
  team_b_name: string;
  team_a_code: string;
  team_b_code: string;
  team_a_flag?: string | null;
  team_b_flag?: string | null;
  team_a_id: number;
  team_b_id: number;
  real_score_a: number | null;
  real_score_b: number | null;
  status: string;
  bracket_slot: string | null;
  match_number?: number | null;
  matchday?: number | null;
  kickoff_time_utc?: string | null;
  stadium?: { name: string; city: string; country: string } | null;
  scoring?: {
    points: number;
    status: "exact" | "outcome" | "wrong";
    predicted: string;
    actual: string;
    reasons?: { label: string; points: number }[];
  } | null;
  prediction?: { score_a: number; score_b: number } | null;
}

export interface TournamentGroup {
  name: string;
  display_order: number;
  teams: { id: number; name: string; code: string; flag_code: string; confederation: string; position: number }[];
}

export interface BracketMatch {
  label: string;
  match_number?: number;
  team_a: { id: number; name: string; code: string } | null;
  team_b: { id: number; name: string; code: string } | null;
  prediction?: { score_a: number; score_b: number };
}

export interface LeaderboardEntry {
  user_id: number;
  name: string;
  username?: string;
  total_score: number;
  group_score: number;
  knockout_score: number;
  special_score: number;
  rank: number;
  rank_change?: number | null;
  daily_points?: number | null;
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    if (typeof detail === "string") throw new Error(detail);
    if (Array.isArray(detail)) {
      const msg = detail.map((d: { msg?: string; loc?: string[] }) => d.msg || JSON.stringify(d)).join("; ");
      throw new Error(msg || "Validation error");
    }
    throw new Error(JSON.stringify(detail));
  }
  return res.json();
}

export const auth = {
  login: (username: string, password: string) =>
    api<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: username.trim().toLowerCase(), password }),
    }),
  register: (username: string, password: string) =>
    api<{ access_token: string; user: User }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username: username.trim().toLowerCase(), password }),
    }),
  me: () => api<User>("/auth/me"),
};

export const dashboard = {
  get: () =>
    api<{
      standings: Record<string, { team_code: string; points: number; goal_difference: number; goals_for: number }[]>;
      latest_results: Match[];
      upcoming_fixtures: Match[];
      leaderboard: { rank: number; name: string; username: string; total_score: number }[];
      stats: {
        total_predictions: number;
        users_with_predictions: number;
        most_predicted_champion: string | null;
        champion_pick_count?: number;
        most_predicted_scorer: string | null;
        scorer_pick_count?: number;
        finished_matches: number;
        total_matches: number;
      };
      team_flags?: Record<string, string>;
    }>("/dashboard"),
};

export const tournament = {
  active: () =>
    api<{ id: number; slug: string; name: string; year: number; format_config: Record<string, unknown> } | null>(
      "/tournament/active"
    ),
  groups: () => api<TournamentGroup[]>("/tournament/groups"),
  settings: () =>
    api<{ predictions_locked: boolean; tournament_started: boolean }>("/tournament/settings"),
};

export const matches = {
  list: (stage?: string, group?: string, matchday?: number) => {
    const params = new URLSearchParams();
    if (stage) params.set("stage", stage);
    if (group) params.set("group", group);
    if (matchday) params.set("matchday", String(matchday));
    const qs = params.toString();
    return api<Match[]>(`/matches${qs ? `?${qs}` : ""}`);
  },
  teams: () =>
    api<{ id: number; name: string; code: string; group_name: string; flag_code: string }[]>("/matches/teams"),
};

export const predictions = {
  status: () => api<{ submitted: boolean; locked: boolean; prediction_count: number }>("/predictions/status"),
  mine: () => api<{ predictions: { match_id: number; predicted_score_a: number; predicted_score_b: number }[]; special: { top_scorer: string | null; top_assister: string | null } }>("/predictions"),
  submit: (data: unknown) =>
    api<{ message: string }>("/predictions/submit", { method: "POST", body: JSON.stringify(data) }),
};

export const leaderboard = {
  list: () => api<LeaderboardEntry[]>("/leaderboard"),
  events: () =>
    api<
      {
        user_name: string;
        points: number;
        label?: string;
        team_a_code?: string;
        team_b_code?: string;
        predicted?: string;
        actual?: string;
      }[]
    >("/leaderboard/events"),
  daily: () => api<{ date: string; rankings: LeaderboardEntry[] }[]>("/leaderboard/daily"),
  me: () =>
    api<{ total_score: number; group_score: number; qualification_score: number; knockout_score: number; special_score: number; chain_bonus: number; breakdown_json: Record<string, unknown> | null }>(
      "/leaderboard/me"
    ),
  breakdown: () =>
    api<{
      summary: Record<string, number>;
      match_scores: {
        match_id?: number;
        match_number?: number;
        stage?: string;
        group_name?: string;
        team_a_code?: string;
        team_b_code?: string;
        predicted: string;
        actual: string;
        points: number;
        status: "exact" | "outcome" | "wrong";
        reasons?: { label: string; points: number }[];
      }[];
      other: { label: string; points: number }[];
    }>("/leaderboard/me/breakdown"),
  standings: () =>
    api<{ group_name: string; standings: Record<string, unknown>[]; qualified_teams: Record<string, unknown>[] }[]>(
      "/leaderboard/standings"
    ),
};

export const simulation = {
  bracket: () =>
    api<{
      qualifiers: Record<string, unknown[]>;
      r32: BracketMatch[];
      bracket: Record<string, BracketMatch[]>;
    }>("/simulation/my-bracket"),
};

export interface AdminUser {
  id: number;
  name: string;
  username: string;
  prediction_count: number;
  is_admin?: boolean;
  created_at?: string;
}

export const admin = {
  users: () => api<AdminUser[]>("/admin/users"),
  matches: () => api<Match[]>("/admin/matches"),
  updateMatch: (id: number, data: Record<string, unknown>) =>
    api<{ message: string }>(`/admin/matches/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  settings: () =>
    api<{
      predictions_locked: boolean;
      tournament_started: boolean;
      actual_top_scorer?: string | null;
      actual_top_assister?: string | null;
      tournament?: { slug: string; name: string };
    }>("/admin/settings"),
  updateSettings: (data: Record<string, unknown>) =>
    api<{ message: string }>("/admin/settings", { method: "PATCH", body: JSON.stringify(data) }),
  recalculate: () => api<{ users_scored: number; leaderboard: unknown[] }>("/admin/recalculate", { method: "POST" }),
  resetPredictions: (userId: number) =>
    api<{ message: string }>(`/admin/users/${userId}/reset-predictions`, { method: "POST" }),
  importTournament: (slug: string, reset = false) =>
    api<{ message: string; teams: number; matches: number }>("/admin/import-tournament", {
      method: "POST",
      body: JSON.stringify({ slug, reset, set_active: true }),
    }),
  validateTournament: (slug: string) =>
    api<{ valid: boolean; errors: string[] }>(`/admin/tournament/validate?slug=${slug}`),
  previewBracket: () => api<{ r32: { label: string; team_a: string; team_b: string }[] }>("/admin/tournament/preview-bracket"),
  listTournaments: () => api<{ id: number; slug: string; name: string; is_active: boolean }[]>("/admin/tournaments"),
  fillRandomResults: () =>
    api<{ message: string }>("/admin/testing/fill-random-results", { method: "POST" }),
  simulateMatchday: () =>
    api<{ message: string }>("/admin/testing/simulate-matchday", { method: "POST" }),
  generateDemoUsers: (count = 10) =>
    api<{ message: string; usernames: string[]; password: string }>(
      `/admin/testing/generate-demo-users?count=${count}`,
      { method: "POST" }
    ),
};
