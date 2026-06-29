/**
 * PostHog analytics helper — thin wrapper around posthog-js.
 * All calls are no-ops when NEXT_PUBLIC_POSTHOG_KEY is not set.
 */
import posthog from "posthog-js";

let _initialized = false;

export function initPostHog(): void {
  if (typeof window === "undefined" || _initialized) return;
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (!key) return;
  posthog.init(key, {
    api_host:        process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://app.posthog.com",
    person_profiles: "identified_only",
    capture_pageview: false,
    autocapture:      false,
  });
  _initialized = true;
}

export function track(event: string, props?: Record<string, unknown>): void {
  if (typeof window !== "undefined" && _initialized) {
    posthog.capture(event, props);
  }
}

export function identifyUser(userId: string, traits?: Record<string, unknown>): void {
  if (typeof window !== "undefined" && _initialized) {
    posthog.identify(userId, traits);
  }
}

export { posthog };
