"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function GithubCallback() {
  const router = useRouter();

  useEffect(() => {
    if (typeof window === "undefined") return;

    const hash = window.location.hash;
    const params = new URLSearchParams(hash.replace(/^#/, ""));
    const token = params.get("token");
    if (token) {
      window.localStorage.setItem("tdq_token", token);
    }
    router.replace("/");
  }, [router]);

  return (
    <main className="min-h-screen flex items-center justify-center">
      <p className="text-gray-400 text-sm">Signing you in with GitHub...</p>
    </main>
  );
}