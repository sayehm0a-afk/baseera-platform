// Sentry (client/browser): opt-in only, mirroring the backend's
// SENTRY_DSN-gated sentry_sdk.init() in ../main.py. NEXT_PUBLIC_SENTRY_DSN
// is unset by default, so Sentry.init() is never called and no network
// call to Sentry is ever attempted in dev, CI, or an unconfigured
// production deployment.
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    // No performance tracing/session replay by default -- this is
    // scaffolding for error visibility, not a decision to sample traces.
    tracesSampleRate: 0,
  });
}

// Required by @sentry/nextjs for App Router navigation instrumentation.
// A no-op when Sentry.init() above never ran (dsn unset).
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
