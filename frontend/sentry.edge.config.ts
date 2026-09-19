// Sentry (Edge runtime, e.g. middleware): opt-in only. See
// instrumentation-client.ts and ../main.py for the same conditional-init
// pattern on the frontend client and the backend, respectively.
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    tracesSampleRate: 0,
  });
}
