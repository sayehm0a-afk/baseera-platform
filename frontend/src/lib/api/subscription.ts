import { apiFetch } from "./client";
import type { MySubscription } from "./subscription-types";

/** Direct, unmodified call to GET /api/v1/subscriptions/me
 * (src/api/routes/subscriptions.py) -- the authenticated user's own
 * subscription state only. */
export function getMySubscription(): Promise<MySubscription> {
  return apiFetch<MySubscription>("/api/v1/subscriptions/me");
}
