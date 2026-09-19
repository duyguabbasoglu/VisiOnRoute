import type { DemoDataStatus, DemoSeedResponse } from "@/lib/schemas";

export const DEMO_DATA_QUERY_KEY = ["demo-data"] as const;

/**
 * Query-key prefixes whose data the synthetic seed changes. Invalidating them
 * makes every mounted panel refetch through the real API after seeding.
 */
export const SEEDED_QUERY_KEYS: readonly (readonly string[])[] = [
  DEMO_DATA_QUERY_KEY,
  ["vehicles"],
  ["drivers"],
  ["assignments"],
  ["fleets"],
  ["data-sources"],
  ["safety-events"],
  ["live"],
  ["trips"],
  ["road-risks"],
  ["coaching"],
  ["subscription-usage"],
];

/**
 * An organization is "empty" when every count the viewer may see is zero.
 * Counts the viewer has no permission for are passed as undefined and ignored;
 * with no visible count at all the dashboard is not considered empty.
 */
export function isDashboardEmpty(counts: Array<number | undefined>): boolean {
  const known = counts.filter((count): count is number => count !== undefined);
  return known.length > 0 && known.every((count) => count === 0);
}

/** Turkish hint for why the seed action is unavailable; null hides the action. */
export function seedUnavailableHint(status: DemoDataStatus | undefined): string | null {
  if (!status || status.available || status.seeded) return null;
  // Outside the demo environment the option does not exist at all.
  if (status.reason === "environment") return null;
  return status.message;
}

export function seedSummaryText(summary: DemoSeedResponse["summary"]): string {
  return (
    `${summary.vehicles} araç, ${summary.drivers} sürücü, ${summary.trips} sefer, ` +
    `${summary.telemetry_points} telemetri noktası, ${summary.safety_events} güvenlik olayı ve ` +
    `${summary.road_risks} yol riski`
  );
}

/**
 * Wraps an async action so overlapping calls share the in-flight promise.
 * Guards against double submission even before React re-renders the button
 * as disabled (e.g. a fast double click).
 */
export function singleFlight<T>(action: () => Promise<T>): () => Promise<T> {
  let inFlight: Promise<T> | null = null;
  return () => {
    if (inFlight) return inFlight;
    inFlight = action().finally(() => {
      inFlight = null;
    });
    return inFlight;
  };
}
