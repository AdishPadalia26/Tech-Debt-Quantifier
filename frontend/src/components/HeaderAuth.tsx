"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { clearToken } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function HeaderAuth() {
  const [user, setUser] = useState<{ login: string; avatar_url?: string } | null>(null);

  useEffect(() => {
    const token = window.localStorage.getItem("tdq_token");
    if (!token) return;
    
    fetch(`${API_URL}/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => res.ok ? res.json() : Promise.reject())
      .then(setUser)
      .catch(() => clearToken());
  }, []);

  const handleLogin = () => {
    window.location.href = `${API_URL}/auth/github/login`;
  };

  const handleLogout = () => {
    clearToken();
    setUser(null);
    window.location.reload();
  };

  return (
    <div className="flex items-center gap-3">
      {user ? (
        <>
          <Link
            href="/import"
            className="text-xs text-green-400 hover:text-green-300"
          >
            Import Repos
          </Link>
          {user.avatar_url && (
            <Image
              src={user.avatar_url}
              alt={user.login}
              width={28}
              height={28}
              className="h-7 w-7 rounded-full border border-gray-600"
            />
          )}
          <span className="text-sm text-gray-200">@{user.login}</span>
          <button onClick={handleLogout} className="text-xs text-gray-400 hover:text-gray-200">
            Sign out
          </button>
        </>
      ) : (
        <button
          onClick={handleLogin}
          className="px-4 py-2 rounded-md bg-green-600 text-white text-sm font-medium hover:bg-green-500"
        >
          Sign in with GitHub
        </button>
      )}
    </div>
  );
}
