"use client";

import { useEffect } from "react";
import { initPostHog } from "@/lib/posthog";

/**
 * Client-side PostHog initializer.
 * Wrap this inside the body in layout.tsx.
 */
export function PostHogProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    initPostHog();
  }, []);

  return <>{children}</>;
}
