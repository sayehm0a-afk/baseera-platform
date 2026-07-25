import { beforeEach, describe, expect, it } from "vitest";
import { getSession, login, logout } from "./temp-auth-service";

describe("temp-auth-service", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns null when no session exists", () => {
    expect(getSession()).toBeNull();
  });

  it("persists a session across login/getSession", () => {
    login("sayehm0a@gmail.com");
    expect(getSession()?.email).toBe("sayehm0a@gmail.com");
  });

  it("clears the session on logout", () => {
    login("sayehm0a@gmail.com");
    logout();
    expect(getSession()).toBeNull();
  });
});
