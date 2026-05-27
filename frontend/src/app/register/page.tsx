"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { auth } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

export default function RegisterPage() {
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
      const { access_token, user } = await auth.register(username, password);
      localStorage.setItem("token", access_token);
      setAuth(access_token, user);
      router.push("/predict");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-md mx-auto px-4 py-16">
      <div className="card">
        <h1 className="text-2xl font-bold mb-6">Register</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm mb-1 text-pitch-200">Username</label>
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} pattern="[a-zA-Z0-9_]+" minLength={3} autoComplete="username" required />
            <p className="text-xs text-pitch-500 mt-1">Letters, numbers, underscores only</p>
          </div>
          <div>
            <label className="block text-sm mb-1 text-pitch-200">Password</label>
            <input type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} minLength={6} autoComplete="new-password" required />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? "Creating account..." : "Create Account"}
          </button>
        </form>
        <p className="mt-4 text-sm text-pitch-300 text-center">
          Already have an account? <Link href="/login" className="text-gold-400 hover:underline">Login</Link>
        </p>
      </div>
    </div>
  );
}
