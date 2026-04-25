"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clearToken, setToken } from "@/lib/api";

export default function GithubCallback() {
  const router = useRouter();
  const [message, setMessage] = useState("Signing you in with GitHub...");

  useEffect(() => {
    if (typeof window === "undefined") return;

    const hash = window.location.hash;
    const params = new URLSearchParams(hash.replace(/^#/, ""));
    const queryParams = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const error = queryParams.get("error");

    if (error) {
      clearToken();
      setMessage(`GitHub sign-in failed: ${decodeURIComponent(error)}`);
      return;
    }

    if (token) {
      setToken(token);
      window.location.replace("/import");
      return;
    }
    clearToken();
    setMessage("GitHub sign-in did not return a valid session token.");
  }, [router]);

  return (
    <main className="min-h-screen flex items-center justify-center">
      <p className="text-gray-400 text-sm">{message}</p>
    </main>
  );
}
