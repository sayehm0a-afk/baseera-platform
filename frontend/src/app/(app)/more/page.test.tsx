import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MorePage from "./page";

/** CONT Phase 7: the mobile "المزيد" tab must resolve to a real page
 * listing every primary nav destination that doesn't already have its
 * own bottom-tab entry -- previously it linked to a route that did
 * not exist. */

describe("MorePage", () => {
  it("lists every primary nav item that has no dedicated mobile tab", () => {
    render(<MorePage />);

    // Has its own bottom tab already -- must not be duplicated here.
    expect(screen.queryByText("الرئيسية")).not.toBeInTheDocument();
    expect(screen.queryByText("المسح")).not.toBeInTheDocument();
    expect(screen.queryByText("المراقبة")).not.toBeInTheDocument();
    expect(screen.queryByText("الأخبار")).not.toBeInTheDocument();

    // No dedicated tab -- must be reachable from here.
    expect(screen.getByText("أفضل الفرص الآن")).toBeInTheDocument();
    expect(screen.getByText("الفرص")).toBeInTheDocument();
    expect(screen.getByText("المحفظة")).toBeInTheDocument();
    expect(screen.getByText("الذكاء الاصطناعي")).toBeInTheDocument();
    expect(screen.getByText("التقارير")).toBeInTheDocument();
    expect(screen.getByText("الاستراتيجيات")).toBeInTheDocument();
    expect(screen.getByText("الإعدادات")).toBeInTheDocument();
  });

  it("links the opportunities item to /opportunities", () => {
    render(<MorePage />);

    expect(screen.getByText("الفرص").closest("a")).toHaveAttribute(
      "href",
      "/opportunities"
    );
  });
});
