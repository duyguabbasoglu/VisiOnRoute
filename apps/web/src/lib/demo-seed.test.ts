import { describe, expect, it } from "vitest";
import {
  DEMO_DATA_QUERY_KEY,
  SEEDED_QUERY_KEYS,
  isDashboardEmpty,
  seedSummaryText,
  seedUnavailableHint,
  singleFlight,
} from "./demo-seed";
import { demoDataStatusSchema, demoSeedResponseSchema, safetyEventSchema } from "./schemas";

describe("synthetic demo seed helpers", () => {
  it("treats an organization as empty only when every visible count is zero", () => {
    expect(isDashboardEmpty([0, 0, 0])).toBe(true);
    expect(isDashboardEmpty([0, undefined, 0])).toBe(true);
    expect(isDashboardEmpty([3, 0, 0])).toBe(false);
    expect(isDashboardEmpty([0, 12, 1])).toBe(false);
    // No permission to see any count: never claim the dashboard is empty.
    expect(isDashboardEmpty([undefined, undefined])).toBe(false);
  });

  it("offers the action only on the demo environment and explains other denials", () => {
    const status = (over: Partial<ReturnType<typeof demoDataStatusSchema.parse>>) =>
      demoDataStatusSchema.parse({ available: false, seeded: false, reason: null, message: null, ...over });

    expect(seedUnavailableHint(status({ available: true }))).toBeNull();
    expect(seedUnavailableHint(status({ reason: "environment", message: "yalnızca demo" }))).toBeNull();
    expect(seedUnavailableHint(status({ seeded: true }))).toBeNull();
    expect(seedUnavailableHint(status({ reason: "role", message: "Yalnızca sahip veya yönetici" }))).toBe(
      "Yalnızca sahip veya yönetici",
    );
    expect(seedUnavailableHint(status({ reason: "email_unverified", message: "Önce doğrulayın" }))).toBe(
      "Önce doğrulayın",
    );
    expect(seedUnavailableHint(undefined)).toBeNull();
  });

  it("refetches every dashboard cache the seed populates", () => {
    const prefixes = SEEDED_QUERY_KEYS.map((key) => key.join("/"));
    for (const key of [DEMO_DATA_QUERY_KEY.join("/"), "vehicles", "drivers", "safety-events", "live", "trips", "road-risks", "data-sources"]) {
      expect(prefixes).toContain(key);
    }
  });

  it("only accepts seed responses explicitly marked synthetic/demo", () => {
    const response = {
      created: true,
      data_origin: "synthetic",
      environment: "demo",
      summary: { vehicles: 3, drivers: 4, trips: 9, telemetry_points: 540, safety_events: 11, road_risks: 2 },
      message: "Sentetik demo verisi oluşturuldu.",
    };
    const parsed = demoSeedResponseSchema.parse(response);
    expect(seedSummaryText(parsed.summary)).toBe(
      "3 araç, 4 sürücü, 9 sefer, 540 telemetri noktası, 11 güvenlik olayı ve 2 yol riski",
    );
    expect(demoSeedResponseSchema.safeParse({ ...response, data_origin: "production" }).success).toBe(false);
    expect(demoSeedResponseSchema.safeParse({ ...response, environment: "production" }).success).toBe(false);
  });

  it("keeps older safety-event payloads valid and reads the synthetic marker", () => {
    const base = {
      id: "e1",
      event_type: "harsh_braking",
      event_label: "Sert fren",
      severity: "high",
      severity_label: "Yüksek",
      confidence: 1,
      occurred_at: "2026-09-19T10:00:00Z",
      vehicle_id: "v1",
      driver_id: null,
      trip_id: null,
      latitude: 39.9,
      longitude: 32.8,
      reason_tr: "Ölçülen yavaşlama 6.1 m/s², eşik 3.5 m/s².",
      review_status: "pending",
      occurrence_count: 1,
      needs_review: false,
    };
    expect(safetyEventSchema.parse(base).data_origin).toBeUndefined();
    expect(safetyEventSchema.parse({ ...base, data_origin: "synthetic" }).data_origin).toBe("synthetic");
  });

  it("prevents double submission by sharing the in-flight request", async () => {
    let calls = 0;
    let release: (value: string) => void = () => undefined;
    const run = singleFlight(() => {
      calls += 1;
      return new Promise<string>((resolve) => {
        release = resolve;
      });
    });

    const first = run();
    const second = run();
    expect(second).toBe(first);
    expect(calls).toBe(1);
    release("ok");
    await expect(first).resolves.toBe("ok");

    // A later, separate click may try again (the server is idempotent).
    const third = run();
    expect(third).not.toBe(first);
    expect(calls).toBe(2);
    release("again");
    await expect(third).resolves.toBe("again");
  });

  it("releases the guard after a failed request so the user can retry", async () => {
    let attempt = 0;
    const run = singleFlight(async () => {
      attempt += 1;
      if (attempt === 1) throw new Error("ağ hatası");
      return "ok";
    });
    await expect(run()).rejects.toThrow("ağ hatası");
    await expect(run()).resolves.toBe("ok");
  });
});
