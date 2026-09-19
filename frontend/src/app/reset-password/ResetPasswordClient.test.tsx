import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("token=abc123"),
  useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock("@/lib/auth/auth-service", () => ({
  resetPassword: vi.fn(),
}));

import { resetPassword } from "@/lib/auth/auth-service";
import { ResetPasswordClient } from "./ResetPasswordClient";

describe("ResetPasswordClient", () => {
  it("shows the password policy up front, before any submit attempt", () => {
    render(<ResetPasswordClient />);

    expect(screen.getByText("8 أحرف على الأقل، تتضمن حرفًا ورقمًا.")).toBeInTheDocument();
  });

  it("rejects a password missing a letter before calling the backend", () => {
    render(<ResetPasswordClient />);

    fireEvent.change(screen.getByLabelText(/^كلمة المرور الجديدة/), {
      target: { value: "12345678" },
    });
    fireEvent.click(screen.getByRole("button", { name: "تحديث كلمة المرور" }));

    expect(
      screen.getByText(/كلمة المرور لا تحقق الشروط المطلوبة/)
    ).toBeInTheDocument();
    expect(resetPassword).not.toHaveBeenCalled();
  });
});
