"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useAuthStore } from "@/lib/store";

const links = [
  { href: "/", label: "Home" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/matches", label: "Matches" },
  { href: "/predict", label: "Predict" },
  { href: "/scores", label: "Scores" },
];

export function Navbar() {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();

  return (
    <nav className="border-b border-pitch-700 bg-pitch-900/95 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-2">
        <Link href="/" className="text-lg sm:text-xl font-bold text-gold-400 flex items-center gap-2 shrink-0">
          ⚽ <span className="hidden sm:inline">World Cup</span>
        </Link>
        <div className="flex items-center gap-0.5 sm:gap-2 overflow-x-auto scrollbar-hide">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={clsx(
                "px-2 sm:px-3 py-1.5 rounded-lg text-xs sm:text-sm whitespace-nowrap transition-colors",
                pathname === l.href ? "bg-pitch-600 text-white" : "text-pitch-100 hover:bg-pitch-800"
              )}
            >
              {l.label}
            </Link>
          ))}
          {user?.is_admin && (
            <Link href="/admin" className="px-2 sm:px-3 py-1.5 rounded-lg text-xs sm:text-sm bg-gold-500/20 text-gold-400 hover:bg-gold-500/30 whitespace-nowrap">
              Admin
            </Link>
          )}
        </div>
        <div className="shrink-0">
          {user ? (
            <div className="flex items-center gap-1 sm:gap-2">
              <span className="text-xs sm:text-sm text-pitch-200 hidden sm:inline">@{user.username}</span>
              <button onClick={logout} className="btn-secondary text-xs sm:text-sm py-1 px-2 sm:px-4">
                Logout
              </button>
            </div>
          ) : (
            <Link href="/login" className="btn-primary text-xs sm:text-sm py-1 px-2 sm:px-4">
              Login
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
