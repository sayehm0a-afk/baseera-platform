import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RegisterPage from "./page";

vi.mock("@/lib/auth/auth-service", () => ({
  register: vi.fn(),
}));

describe("RegisterPage", () => {
  it("shows the honest, no-profit-guarantee value-prop tagline above the signup form", () => {
    render(<RegisterPage />);

    expect(
      screen.getByText(/بصيرة يحلل السوق السعودي بالذكاء الاصطناعي ويعطيك توصية واضحة/)
    ).toBeInTheDocument();
    expect(screen.getByText(/القرار النهائي دائمًا لك/)).toBeInTheDocument();
  });
});
