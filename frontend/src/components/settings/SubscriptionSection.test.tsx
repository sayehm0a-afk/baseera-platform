import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SubscriptionSection } from "./SubscriptionSection";
import type { MySubscription } from "@/lib/api/subscription-types";

vi.mock("@/lib/api/subscription", () => ({
  getMySubscription: vi.fn(),
}));

import { getMySubscription } from "@/lib/api/subscription";

function buildSubscription(overrides: Partial<MySubscription> = {}): MySubscription {
  return {
    plan: "TRIAL",
    status: "TRIALING",
    trial_ends_at: "2026-09-30T00:00:00Z",
    current_period_start: "2026-09-01T00:00:00Z",
    current_period_end: "2026-09-30T00:00:00Z",
    cancel_at_period_end: false,
    ...overrides,
  };
}

describe("SubscriptionSection", () => {
  it("shows the Arabic plan and status labels for a trialing user", async () => {
    vi.mocked(getMySubscription).mockResolvedValue(buildSubscription());

    render(<SubscriptionSection />);

    expect(await screen.findByText("تجريبي")).toBeInTheDocument();
    expect(screen.getByText("فترة تجريبية")).toBeInTheDocument();
    expect(screen.getByText("تنتهي الفترة التجريبية في")).toBeInTheDocument();
  });

  it("tells a fully-entitled user that all core features are unrestricted -- never invents a feature-tier that does not exist", async () => {
    vi.mocked(getMySubscription).mockResolvedValue(buildSubscription({ plan: "MONTHLY", status: "ACTIVE" }));

    render(<SubscriptionSection />);

    expect(await screen.findByText("شهري")).toBeInTheDocument();
    expect(screen.getByText("نشط")).toBeInTheDocument();
    expect(screen.getByText("تتجدد الباقة في")).toBeInTheDocument();
    expect(screen.getByText(/جميع ميزات بصيرة الأساسية/)).toBeInTheDocument();
  });

  it("shows the cancellation notice when cancel_at_period_end is set", async () => {
    vi.mocked(getMySubscription).mockResolvedValue(
      buildSubscription({ plan: "YEARLY", status: "CANCELED", cancel_at_period_end: true })
    );

    render(<SubscriptionSection />);

    expect(await screen.findByText("ملغى")).toBeInTheDocument();
    expect(screen.getByText("ينتهي الوصول في")).toBeInTheDocument();
    expect(screen.getByText(/تم إلغاء التجديد التلقائي/)).toBeInTheDocument();
    // CANCELED is still an entitled status until the period actually
    // ends -- must not be told access is already lost.
    expect(screen.getByText(/جميع ميزات بصيرة الأساسية/)).toBeInTheDocument();
  });

  it("honestly tells an expired user that core features are locked, not a fabricated limited tier", async () => {
    vi.mocked(getMySubscription).mockResolvedValue(
      buildSubscription({ status: "EXPIRED", trial_ends_at: null, current_period_end: null })
    );

    render(<SubscriptionSection />);

    expect(await screen.findByText("منتهٍ")).toBeInTheDocument();
    expect(screen.getByText(/متوقف حتى تجديد الاشتراك/)).toBeInTheDocument();
    expect(screen.queryByText(/جميع ميزات بصيرة الأساسية/)).not.toBeInTheDocument();
  });

  it("shows a staff account's synthetic subscription honestly", async () => {
    vi.mocked(getMySubscription).mockResolvedValue(
      buildSubscription({
        plan: "STAFF",
        status: "ACTIVE",
        trial_ends_at: null,
        current_period_start: null,
        current_period_end: null,
      })
    );

    render(<SubscriptionSection />);

    expect(await screen.findByText("حساب فريق العمل")).toBeInTheDocument();
    expect(screen.getByText("نشط")).toBeInTheDocument();
  });

  it("shows an error state when the fetch fails", async () => {
    vi.mocked(getMySubscription).mockRejectedValue(new Error("network error"));

    render(<SubscriptionSection />);

    expect(await screen.findByText("تعذّر تحميل بيانات الباقة")).toBeInTheDocument();
  });
});
