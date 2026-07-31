import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionControls } from "@/components/session-controls";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SessionControls", () => {
  it("sends the session-bound CSRF proof when signing out", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<SessionControls csrfToken="csrf-proof" />);

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/sign-out", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": "csrf-proof" },
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Sign-out failed");
  });

  it("sanitizes network failure without exposing internal details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockRejectedValue(new Error("private")),
    );
    render(<SessionControls csrfToken="csrf-proof" />);
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Sign-out failed"),
    );
    expect(document.body.textContent).not.toContain("private");
  });
});
