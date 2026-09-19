import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { register } from "@/lib/auth/auth-service";
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

  it("shows the password policy up front, before any submit attempt", () => {
    render(<RegisterPage />);

    expect(screen.getByText("8 أحرف على الأقل، تتضمن حرفًا ورقمًا.")).toBeInTheDocument();
  });

  it("rejects a password missing a digit before calling the backend", () => {
    render(<RegisterPage />);

    fireEvent.change(screen.getByLabelText("البريد الإلكتروني"), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/^كلمة المرور/), {
      target: { value: "onlyletters" },
    });
    fireEvent.click(screen.getByRole("button", { name: "إنشاء حساب" }));

    expect(
      screen.getByText(/كلمة المرور لا تحقق الشروط المطلوبة/)
    ).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });
});
