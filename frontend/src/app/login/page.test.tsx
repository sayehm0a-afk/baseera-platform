import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import LoginPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock("@/lib/auth/auth-service", () => ({
  login: vi.fn(),
}));

describe("LoginPage", () => {
  it("shows the same brand tagline as the register page", () => {
    render(<LoginPage />);

    expect(screen.getByText("الذكاء الاصطناعي يحلل السوق السعودي، وأنت تقرر.")).toBeInTheDocument();
  });
});
