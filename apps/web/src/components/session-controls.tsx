"use client";

import { useState } from "react";

export function SessionControls({ csrfToken }: { csrfToken: string }) {
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function signOut(): Promise<void> {
    setPending(true);
    setFailed(false);
    try {
      const response = await fetch("/api/auth/sign-out", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrfToken },
      });
      if (!response.ok) {
        setFailed(true);
        setPending(false);
        return;
      }
      window.location.assign("/");
    } catch {
      setFailed(true);
      setPending(false);
    }
  }

  return (
    <div className="mt-5 flex flex-wrap items-center gap-3">
      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800">
        Synthetic reviewer signed in
      </span>
      <button
        type="button"
        disabled={pending}
        className="rounded-lg px-3 py-1 text-sm font-semibold text-slate-600 hover:bg-slate-100 hover:text-slate-950 disabled:opacity-50"
        onClick={() => void signOut()}
      >
        {pending ? "Signing out…" : "Sign out"}
      </button>
      {failed ? (
        <span role="alert" className="text-sm text-red-700">
          Sign-out failed. Please retry.
        </span>
      ) : null}
    </div>
  );
}
