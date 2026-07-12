"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function GithubCallback() {
  const router = useRouter();
  const [message, setMessage] = useState("Signing you in with GitHub...");

  useEffect(() => {
    if (typeof window === "undefined") return;

    const queryParams = new URLSearchParams(window.location.search);
    const error = queryParams.get("error");

    if (error) {
      setMessage(`GitHub sign-in failed: ${decodeURIComponent(error)}`);
      return;
    }

    // Cookie is set by the backend redirect — just navigate.
    window.location.replace("/import");
  }, [router]);

  return (
    <main className="min-h-screen flex items-center justify-center">
      <p className="text-gray-400 text-sm">{message}</p>
    </main>
  );
}
