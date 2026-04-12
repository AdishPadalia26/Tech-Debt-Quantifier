"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { GitBranch, LogOut, Plus } from "lucide-react";

import { clearToken } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function HeaderAuth() {
  const [user, setUser] = useState<{ login: string; avatar_url?: string } | null>(null);

  useEffect(() => {
    const token = window.localStorage.getItem("tdq_token");
    if (!token) return;

    fetch(`${API_URL}/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
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
          <Button variant="outline" size="sm" asChild>
            <Link href="/import">
              <Plus className="mr-2 size-4" />
              Import Repos
            </Link>
          </Button>
          {user.avatar_url && (
            <Image
              src={user.avatar_url}
              alt={user.login}
              width={32}
              height={32}
              className="size-8 rounded-full border border-border"
            />
          )}
          <Badge variant="outline" className="hidden sm:inline-flex">
            @{user.login}
          </Badge>
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            <LogOut className="mr-2 size-4" />
            Sign out
          </Button>
        </>
      ) : (
        <Button size="sm" onClick={handleLogin}>
          <GitBranch className="mr-2 size-4" />
          Sign in with GitHub
        </Button>
      )}
    </div>
  );
}
