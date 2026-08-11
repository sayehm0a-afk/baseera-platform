import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FreshnessBanner } from "./FreshnessBanner";

/** CONT Phase 6: the /today freshness/provenance disclosure. Every
 * state renders the backend's own Arabic label verbatim -- this
 * component never re-derives freshness from data_age_hours itself. */

describe("FreshnessBanner", () => {
  it("renders the fresh state label and the last-scan timestamp", () => {
    render(
      <FreshnessBanner
        result={{
          generated_at: "2026-08-11T10:00:00Z",
          data_age_hours: 1,
          freshness_state: "FRESH",
          freshness_label_ar: "بيانات حديثة",
        }}
      />
    );

    expect(screen.getByText("بيانات حديثة")).toBeInTheDocument();
    expect(screen.getByText(/آخر مسح:/)).toBeInTheDocument();
    expect(screen.getByText("(منذ 1 ساعة)")).toBeInTheDocument();
  });

  it("renders the aging state distinctly from fresh and stale", () => {
    render(
      <FreshnessBanner
        result={{
          generated_at: "2026-08-11T10:00:00Z",
          data_age_hours: 15,
          freshness_state: "AGING",
          freshness_label_ar: "بيانات آخذة في التقادم لكنها لا تزال مفيدة",
        }}
      />
    );

    expect(screen.getByText("بيانات آخذة في التقادم لكنها لا تزال مفيدة")).toBeInTheDocument();
  });

  it("renders the stale state", () => {
    render(
      <FreshnessBanner
        result={{
          generated_at: "2026-08-10T10:00:00Z",
          data_age_hours: 30,
          freshness_state: "STALE",
          freshness_label_ar: "بيانات قديمة جدًا لإصدار توصية جديدة",
        }}
      />
    );

    expect(screen.getByText("بيانات قديمة جدًا لإصدار توصية جديدة")).toBeInTheDocument();
  });

  it("renders the no-scan state without a timestamp or age, never a fabricated one", () => {
    render(
      <FreshnessBanner
        result={{
          generated_at: null,
          data_age_hours: null,
          freshness_state: "NO_SCAN",
          freshness_label_ar: "لا يوجد مسح سابق للسوق",
        }}
      />
    );

    expect(screen.getByText("لا يوجد مسح سابق للسوق")).toBeInTheDocument();
    expect(screen.queryByText(/آخر مسح:/)).not.toBeInTheDocument();
  });

  it("formats a sub-hour age in minutes rather than rounding to zero hours", () => {
    render(
      <FreshnessBanner
        result={{
          generated_at: "2026-08-11T10:00:00Z",
          data_age_hours: 0.25,
          freshness_state: "FRESH",
          freshness_label_ar: "بيانات حديثة",
        }}
      />
    );

    expect(screen.getByText("(منذ 15 دقيقة)")).toBeInTheDocument();
  });
});
