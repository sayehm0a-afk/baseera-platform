import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchSession,
  forgotPassword,
  getSessionSnapshot,
  login,
  logout,
  logoutAll,
  register,
  resetPassword,
  verifyEmail,
} from "./auth-service";

const AUTH_USER = {
  id: 1,
  email: "sayehm0a@gmail.com",
  full_name: null,
  is_email_verified: true,
  is_staff: false,
  staff_role: null,
  created_at: "2026-01-01T00:00:00Z",
  last_login_at: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

describe("auth-service", () => {
  beforeEach(() => {
    // Every test starts from "not yet resolved" -- fetchSession() is
    // what actually resolves it, exactly like a fresh page load.
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetchSession resolves to the user on success", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(AUTH_USER));
    const user = await fetchSession();
    expect(user?.email).toBe(AUTH_USER.email);
    expect(getSessionSnapshot()?.email).toBe(AUTH_USER.email);
  });

  it("fetchSession resolves to null (never throws) when unauthenticated", async () => {
    // A fresh Response per call -- a 401 here also triggers apiFetch's
    // internal refresh-and-retry attempt (a second fetch call), and a
    // Response body can only be read once.
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(() =>
      Promise.resolve(
        jsonResponse({ error: { code: "unauthenticated", message: "no" } }, 401)
      )
    );
    const user = await fetchSession();
    expect(user).toBeNull();
    expect(getSessionSnapshot()).toBeNull();
  });

  it("register posts email/password and returns the created user", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(AUTH_USER, 201));
    const user = await register("sayehm0a@gmail.com", "s3cret-password");
    expect(user.email).toBe(AUTH_USER.email);

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({
      email: "sayehm0a@gmail.com",
      password: "s3cret-password",
    });
  });

  it("verifyEmail posts the token", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse({ message: "ok" }));
    await verifyEmail("raw-token");
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ token: "raw-token" });
  });

  it("login calls /login then resolves the session from /me", async () => {
    (fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(jsonResponse({ message: "ok" })) // /login
      .mockResolvedValueOnce(jsonResponse(AUTH_USER)); // /me
    const user = await login("sayehm0a@gmail.com", "s3cret-password");
    expect(user.email).toBe(AUTH_USER.email);
    expect(getSessionSnapshot()?.email).toBe(AUTH_USER.email);
  });

  it("logout clears the session even if the request fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(AUTH_USER));
    await fetchSession();
    expect(getSessionSnapshot()).not.toBeNull();

    (fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("network down"));
    await expect(logout()).rejects.toThrow();
    expect(getSessionSnapshot()).toBeNull();
  });

  it("logoutAll clears the session on success", async () => {
    (fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(jsonResponse(AUTH_USER)) // seed a session
      .mockResolvedValueOnce(jsonResponse({ message: "ok" })); // /logout-all
    await fetchSession();
    await logoutAll();
    expect(getSessionSnapshot()).toBeNull();
  });

  it("forgotPassword posts the email", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse({ message: "ok" }));
    await forgotPassword("sayehm0a@gmail.com");
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ email: "sayehm0a@gmail.com" });
  });

  it("resetPassword posts token/new_password and clears any cached session", async () => {
    (fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(jsonResponse(AUTH_USER)) // seed a session
      .mockResolvedValueOnce(jsonResponse({ message: "ok" })); // /reset-password
    await fetchSession();
    await resetPassword("raw-token", "brand-new-password");

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[1];
    expect(JSON.parse(init.body)).toEqual({
      token: "raw-token",
      new_password: "brand-new-password",
    });
    expect(getSessionSnapshot()).toBeNull();
  });
});
