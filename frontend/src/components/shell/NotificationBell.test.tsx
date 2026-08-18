import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NotificationBell } from "./NotificationBell";
import type { Notification } from "@/lib/api/notification-types";

vi.mock("@/lib/api/notifications", () => ({
  listNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));

import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/api/notifications";

function notification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: 1,
    type: "MARKET_ALERT",
    title: "تنبيه 2222",
    body: "خطر مرتفع بسبب أخبار سلبية",
    read_at: null,
    created_at: "2026-08-18T00:00:00Z",
    ...overrides,
  };
}

describe("NotificationBell", () => {
  it("shows no unread badge when there are no notifications", async () => {
    vi.mocked(listNotifications).mockResolvedValue({ notifications: [], unread_count: 0 });

    render(<NotificationBell />);

    await waitFor(() => expect(listNotifications).toHaveBeenCalled());
    expect(screen.queryByText("9+")).not.toBeInTheDocument();
  });

  it("shows the real unread count as a badge", async () => {
    vi.mocked(listNotifications).mockResolvedValue({
      notifications: [notification()],
      unread_count: 3,
    });

    render(<NotificationBell />);

    expect(await screen.findByText("3")).toBeInTheDocument();
  });

  it("opens the dropdown and lists real notifications on click", async () => {
    vi.mocked(listNotifications).mockResolvedValue({
      notifications: [notification({ title: "تنبيه هام" })],
      unread_count: 1,
    });

    render(<NotificationBell />);
    fireEvent.click(screen.getByRole("button", { name: "التنبيهات" }));

    expect(await screen.findByText("تنبيه هام")).toBeInTheDocument();
  });

  it("shows an honest empty state instead of fabricating notifications", async () => {
    vi.mocked(listNotifications).mockResolvedValue({ notifications: [], unread_count: 0 });

    render(<NotificationBell />);
    fireEvent.click(screen.getByRole("button", { name: "التنبيهات" }));

    expect(await screen.findByText("لا توجد تنبيهات بعد")).toBeInTheDocument();
  });

  it("marks a single notification read on click and decrements the unread count", async () => {
    vi.mocked(listNotifications).mockResolvedValue({
      notifications: [notification()],
      unread_count: 1,
    });
    vi.mocked(markNotificationRead).mockResolvedValue(
      notification({ read_at: "2026-08-18T01:00:00Z" })
    );

    render(<NotificationBell />);
    fireEvent.click(screen.getByRole("button", { name: "التنبيهات" }));
    fireEvent.click(await screen.findByText("تنبيه 2222"));

    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledWith(1));
    await waitFor(() => expect(screen.queryByText("1")).not.toBeInTheDocument());
  });

  it("marks all notifications read via the bulk action", async () => {
    vi.mocked(listNotifications).mockResolvedValue({
      notifications: [notification(), notification({ id: 2 })],
      unread_count: 2,
    });
    vi.mocked(markAllNotificationsRead).mockResolvedValue({ message: "تم" });

    render(<NotificationBell />);
    fireEvent.click(screen.getByRole("button", { name: "التنبيهات" }));

    fireEvent.click(await screen.findByText("تعليم الكل كمقروء"));

    await waitFor(() => expect(markAllNotificationsRead).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText("تعليم الكل كمقروء")).not.toBeInTheDocument());
  });
});
