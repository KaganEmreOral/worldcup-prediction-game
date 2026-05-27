"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { auth } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { access_token } = await auth.login(username, password);
      localStorage.setItem("token", access_token);
      const user = await auth.me();
      setAuth(access_token, user);
      router.push(user.is_admin ? "/admin" : "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-md mx-auto px-4 py-16">
      <div className="card">
        <h1 className="text-2xl font-bold mb-6">Login</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm mb-1 text-pitch-200">Username</label>
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
          </div>
          <div>
            <label className="block text-sm mb-1 text-pitch-200">Password</label>
            <input type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
        <p className="mt-4 text-sm text-pitch-300 text-center">
          No account? <Link href="/register" className="text-gold-400 hover:underline">Register</Link>
        </p>
      </div>
    </div>
  );
}
