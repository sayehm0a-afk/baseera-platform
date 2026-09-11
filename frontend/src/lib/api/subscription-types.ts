/** Mirrors src/api/schemas/subscriptions.py's SubscriptionOut --
 * GET /api/v1/subscriptions/me, the authenticated user's OWN
 * trial/subscription state (never another user's -- that's the
 * separate, staff-only AdminSubscription in admin-types.ts). No
 * payment gateway is integrated in this codebase yet
 * (src/billing/provider.py is the seam for one) -- this must never
 * imply real payment processing. */
export interface MySubscription {
  plan: string;
  status: string;
  trial_ends_at: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
}
