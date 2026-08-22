import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

// useSyncExternalStore requires a stable snapshot reference across
// calls -- a new object literal every render causes an infinite
// re-render loop, so the fixture is defined once outside the mock.
const sessionSnapshot = {
  email: "user@example.com",
  last_login_at: "2026-08-01T10:00:00Z",
};

vi.mock("@/lib/auth/auth-service", () => ({
  logout: vi.fn(),
  logoutAll: vi.fn(),
  getSessionSnapshot: () => sessionSnapshot,
  getSessionServerSnapshot: () => null,
  subscribeToSession: () => () => {},
}));

import SettingsPage from "./page";
import { logout, logoutAll } from "@/lib/auth/auth-service";

describe("SettingsPage logout", () => {
  it("navigates to login on a successful logout", async () => {
    vi.mocked(logout).mockResolvedValue(undefined);

    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "تسجيل الخروج" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("recovers from a network failure instead of leaving the sign-out button permanently disabled", async () => {
    vi.mocked(logout).mockRejectedValue(new Error("network error"));

    render(<SettingsPage />);
    const button = screen.getByRole("button", { name: "تسجيل الخروج" });
    fireEvent.click(button);

    expect(
      await screen.findByText(/تعذّر تسجيل الخروج عبر الخادم بسبب مشكلة في الاتصال/)
    ).toBeInTheDocument();

    // The soft-lock bug: isSigningOut never reset, both buttons stayed
    // disabled forever. Verify recovery -- the button is clickable again.
    await waitFor(() => expect(button).not.toBeDisabled());
  });

  it("offers a manual continue-to-login action after a failed logout, since the local session is already gone either way", async () => {
    vi.mocked(logout).mockRejectedValue(new Error("network error"));

    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "تسجيل الخروج" }));

    fireEvent.click(await screen.findByRole("button", { name: "المتابعة إلى صفحة الدخول" }));
    expect(replace).toHaveBeenCalledWith("/login");
  });

  it("also recovers logout-all from a network failure", async () => {
    vi.mocked(logoutAll).mockRejectedValue(new Error("network error"));

    render(<SettingsPage />);
    const button = screen.getByRole("button", { name: "تسجيل الخروج من جميع الأجهزة" });
    fireEvent.click(button);

    expect(
      await screen.findByText(/تعذّر تسجيل الخروج من جميع الأجهزة عبر الخادم بسبب مشكلة في الاتصال/)
    ).toBeInTheDocument();
    await waitFor(() => expect(button).not.toBeDisabled());
  });
});
