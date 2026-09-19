// Next.js server instrumentation hook. Loads Sentry's per-runtime config
// (each of which is itself gated on NEXT_PUBLIC_SENTRY_DSN) and, when
// Sentry is configured, forwards server-side rendering errors to it.
// Entirely inert when NEXT_PUBLIC_SENTRY_DSN is unset.
import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (!process.env.NEXT_PUBLIC_SENTRY_DSN) {
    return;
  }

  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }

  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

export const onRequestError = Sentry.captureRequestError;
