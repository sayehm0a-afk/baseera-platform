# Subscription & Trial Entitlements (Phase 13, P13.5)

An end-to-end audit of what actually gates access to Baseerah's paid
product, prompted by the Phase 13 requirement to verify trial/
subscription enforcement is real and complete -- not just present
somewhere in the codebase. This document covers what was found, what
was fixed, and the entitlement status of every route in the API.

## 1. The critical finding: two entire route files had no auth at all

`src/api/routes/market.py` and `src/api/routes/stocks.py` -- covering
live quotes, technical/fundamental analysis, the full AI recommendation/
decision/analyst-report stack, market scans, rankings, top-buy/
top-strong-buy lists, sector data, change events, and alerts -- had
**zero** authentication dependency on any route. No `Depends
(get_current_user)`, no `require_active_subscription()`, nothing.

This meant any anonymous caller on the open internet could hit these
endpoints directly and receive Baseerah's entire AI-driven product for
free, with no account, no trial, no subscription, and no rate limit
beyond whatever global default exists. The frontend's `RequireSession`
guard (`frontend/src/components/auth/RequireSession.tsx`) never
protected this -- it is client-side React routing that redirects an
unauthenticated *browser tab* to `/login`; it has no effect on a direct
API call (`curl`, a script, a competitor scraping the product) that
never loads the frontend at all. This is exactly the failure mode the
Phase 13 brief's non-negotiable rule "never trust frontend entitlement
checks" describes.

**Root cause**: the Phase 10 plan (which introduced auth/subscriptions)
left a placeholder reference to a "Which endpoints" section spelling out
the free-vs-premium split, but that section was never actually written
before Phase 10 was executed -- `portfolio.py` correctly got
authentication (ownership-scoped) and `backtests.py` correctly got
`require_active_subscription()`, but `market.py`/`stocks.py` were
simply never revisited.

### The fix

Every route in both files now depends on
`Depends(require_active_subscription())` (`src/auth/rbac.py`) --
the same dependency `backtests.py` already used correctly. This:

- Gives staff (`is_staff=True`) an unconditional bypass.
- Is satisfied by `TRIALING`, `ACTIVE`, or a still-within-period
  `CANCELED` subscription -- i.e. **every real trial or paying
  customer is unaffected**. Since every new registration automatically
  gets a 14-day trial (`subscription_service.provision_trial_
  subscription`, called from `user_service.register`), this fix costs
  zero real users any access; it only closes the anonymous/expired-user
  hole.
- Rejects with `401` (no credentials at all) or `402 Payment Required`
  (`subscription_required`, authenticated but not entitled) -- never a
  silent degradation or a partial response.

Verified by `tests/integration/api/test_market_data_subscription_gating.py`
(new): anonymous -> 401, authenticated-no-subscription -> 402,
authenticated-expired-subscription -> 402, authenticated-real-trial ->
passes the entitlement check. Every pre-existing test in
`test_stocks_routes.py`, `test_market_routes.py`,
`test_recommendation_route.py`, `test_decision_route.py`,
`test_analyst_report_route.py`, and `test_portfolio_routes.py` (which
also calls `/api/v1/market/scan` directly) was updated to authenticate
as a staff user (or, for `test_portfolio_routes.py`, to provision a real
trial subscription for its test customer) so the tests keep exercising
route *behavior*, not auth setup -- see each file's own updated
docstring/comment for the exact reasoning.

## 2. Full route-by-route entitlement table

| Router | Gate | Status |
|---|---|---|
| `stocks.py` (`/quote`, `/history`, `/technical`, `/fundamentals`, `/recommendation`, `/decision`, `/analyst-report`, base `/{symbol}`) | `require_active_subscription()` | **Fixed in P13.5** (previously: none) |
| `market.py` (`/scan`, `/summary`, `/rankings`, `/top-buy`, `/top-strong-buy`, `/watchlists`, `/sectors`, `/changes`, `/alerts`) | `require_active_subscription()` | **Fixed in P13.5** (previously: none) |
| `backtests.py` (all routes) | `require_active_subscription()` | Already correct (Phase 10 M10.6) |
| `calibrations.py` (all routes) | `require_staff_role(StaffRole.SUPPORT)` | Already correct (Phase 10 decision 10 -- tuning/activation is an ops action, not a customer feature; deliberately not subscription-gated) |
| `portfolio.py` (all routes) | `get_current_user` (ownership-scoped, ID in path checked against caller) | Already correct (Phase 10 M10.5) -- authenticated, not subscription-gated: a customer's own portfolio data is not withheld mid-trial-expiry the way a market-wide AI feature is |
| `news.py` `/market`, `/{symbol}` | `get_current_user` | Already correct, disclosed by design (the file's own docstring: "plain reads open to any authenticated user," mirroring `calibrations.py`'s "staff-only for anything that spends real quota/LLM budget" split) |
| `news.py` `/sources`, `/refresh` | `require_staff_role(StaffRole.SUPPORT)` | Already correct -- `/refresh` spends real LLM budget |
| `subscriptions.py` `/me` | `get_current_user` | Correct by construction -- a user must be able to see their own subscription status regardless of what it is |
| `auth.py` (all routes) | Route-specific (some are pre-login by necessity: register/login/forgot-password/reset-password/verify-email) | Out of scope here -- covered by `docs/AUTHENTICATION_SECURITY.md` |
| `admin/*` (all routers) | `require_staff_role(...)` | Out of scope here -- covered by `docs/ADMIN_AND_RBAC.md` |

## 3. Subscription lifecycle correctness (cross-referenced from P13.4)

`_ENTITLED_STATUSES` (`src/subscriptions/subscription_service.py`) is
`(TRIALING, ACTIVE, CANCELED)`. The `CANCELED` inclusion was a P13.4 fix
(a subscription cancelled "at period end," the default admin action,
must keep the customer entitled until the period actually ends) --
see `docs/ADMIN_AND_RBAC.md` §1 for the full writeup; this document
doesn't repeat it, only confirms it composes correctly with the
`market.py`/`stocks.py` fix above (a `CANCELED`-but-still-within-period
customer is not newly locked out by this milestone's changes).

`get_effective_subscription()` lazily reconciles `status` against
`current_period_end` on every call (Phase 10 decision 9) -- there is no
scheduler dependency for correctness, and therefore no clock-skew or
concurrency edge case beyond ordinary request-level atomicity: two
concurrent requests for the same expired subscription both compute the
same "expired" answer and issue idempotent identical writes (`UPDATE
... SET status = 'EXPIRED'`), so a race between them is harmless.

## 4. `PAST_DUE`: defined, not yet reachable (disclosed, not a bug)

`SubscriptionStatus.PAST_DUE` exists in the enum
(`src/domain/models/subscription.py`) but no code path anywhere sets
it. This is a direct, correct consequence of the billing architecture
being interface-only (`src/billing/provider.py`'s `IPaymentProvider`
has exactly one implementation, `NoopPaymentProvider`, which never
represents a real recurring charge) -- `PAST_DUE` is what a real
payment gateway's "recurring charge failed" webhook would set, and no
such webhook can ever fire without a real gateway integration
(`docs/PAYMENT_PROVIDER_INTEGRATION.md`, P13.6). Fabricating a
`PAST_DUE` transition without a real failed-charge signal behind it
would be exactly the kind of invented backend behavior the Phase 13
brief rules out. Left as a disclosed gap, not implemented here: once a
real gateway exists, a decision is still needed on whether `PAST_DUE`
grants a grace period (should it be added to `_ENTITLED_STATUSES`?) or
blocks access immediately -- deferred to that milestone since it's a
product decision, not an engineering one.

## 5. `SUSPENDED`/`COMPLIMENTARY` statuses (Phase 13 spec mention)

Not added in this milestone -- see `docs/ADMIN_AND_RBAC.md` §5 for the
reasoning (suspension is already modeled at `User.is_active`, and
`admin_activate_subscription` already serves the comped-account case
without a distinct status).

## 6. Frontend never makes an entitlement decision the backend doesn't enforce

Audited `frontend/src/lib/api/client.ts` (`apiFetch` always sends
`credentials: "include"`) and every page under
`frontend/src/app/(app)/`: no screen makes a client-side "is this user
entitled" branch that isn't backed by a real API response. The only
gate on the frontend side is `RequireSession` (session existence, not
entitlement), which is a UX convenience (skip the loading flicker,
redirect to `/login` instead of showing a raw 401/402 page) --
never the actual security boundary, which is `require_active_
subscription()` on every route table in §2 above. A user whose trial
has expired still reaches these screens through the frontend router;
the *data* they need never arrives, because the backend rejects it,
exactly as intended.

See `docs/ADMIN_AND_RBAC.md` for the RBAC/staff side of access control,
and `docs/AUTHENTICATION_SECURITY.md` for the customer-authentication
audit this document's entitlement section builds on.
