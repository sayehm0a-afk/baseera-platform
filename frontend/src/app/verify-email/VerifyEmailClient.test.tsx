import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/auth/auth-service", () => ({
  verifyEmail: vi.fn(),
  resendVerification: vi.fn(),
}));

import { VerifyEmailClient } from "./VerifyEmailClient";
import { resendVerification } from "@/lib/auth/auth-service";

describe("VerifyEmailClient -- no token (invalid/expired link)", () => {
  it("shows a resend-verification form and submits the entered email", async () => {
    vi.mocked(resendVerification).mockResolvedValue(undefined);

    render(<VerifyEmailClient />);

    expect(screen.getByText("رابط التأكيد غير صالح أو منتهي الصلاحية.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("البريد الإلكتروني"), {
      target: { value: "user@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "إعادة إرسال رابط التأكيد" }));

    await waitFor(() => expect(resendVerification).toHaveBeenCalledWith("user@example.com"));
    expect(
      await screen.findByText(
        "إذا كان هذا البريد الإلكتروني مسجّلاً وغير مؤكَّد بعد، فستصلك رسالة تحتوي على رابط تأكيد جديد."
      )
    ).toBeInTheDocument();
  });
});
