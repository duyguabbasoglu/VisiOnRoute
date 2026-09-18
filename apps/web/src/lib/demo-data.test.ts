import { describe, expect, it } from "vitest";
import {
  DEMO_DATA_ORIGIN,
  DEMO_DRIVERS,
  DEMO_ENVIRONMENT,
  DEMO_EVENTS,
  DEMO_HOURLY_EVENTS_24H,
  DEMO_TYPE_COUNTS_24H,
  DEMO_VEHICLES,
  DEMO_VEHICLE_TOTAL,
  activeVehicleCount,
  averageRiskIndex,
  driverRanking,
  driverRisk,
  explainEvent,
  relativeMinutes,
  totalEvents24h,
} from "./demo-data";

describe("public demo fixtures", () => {
  it("are marked synthetic and demo-only", () => {
    expect(DEMO_DATA_ORIGIN).toBe("synthetic");
    expect(DEMO_ENVIRONMENT).toBe("demo");
    // Fictional plate series and pseudonymous drivers only.
    for (const v of DEMO_VEHICLES) {
      expect(v.plate).toMatch(/^\d{2} DMO \d{3}$/);
      expect(v.driver).toMatch(/^Sürücü D-\d{2}$/);
    }
  });

  it("keep every 24-hour breakdown consistent with the headline count", () => {
    const total = totalEvents24h();
    expect(total).toBe(126);
    expect(Object.values(DEMO_TYPE_COUNTS_24H).reduce((a, b) => a + b, 0)).toBe(total);
    expect(DEMO_HOURLY_EVENTS_24H).toHaveLength(24);
    expect(DEMO_HOURLY_EVENTS_24H.reduce((a, b) => a + b, 0)).toBe(total);
  });

  it("only reference vehicles that exist and never exceed the fleet size", () => {
    const plates = new Set(DEMO_VEHICLES.map((v) => v.plate));
    for (const event of DEMO_EVENTS) expect(plates.has(event.vehicle)).toBe(true);
    expect(activeVehicleCount()).toBeLessThanOrEqual(DEMO_VEHICLE_TOTAL);
    expect(new Set(DEMO_EVENTS.map((e) => e.id)).size).toBe(DEMO_EVENTS.length);
  });

  it("scores drivers with the backend's exposure-normalised formula", () => {
    const d07 = driverRisk(DEMO_DRIVERS[0]!);
    // (10·1 + 7·2.5 + 5·5 + 1·9) / 12.4 = 4.96 weighted events per 100 km
    expect(d07.weightedEvents).toBe(61.5);
    expect(d07.riskIndex).toBeCloseTo(4.96, 2);
    expect(d07.score).toBeCloseTo(100 * Math.exp(-4.96 / 14.43), 1);
  });

  it("withholds a score below the minimum exposure", () => {
    const short = driverRisk({ code: "Sürücü D-99", exposureKm: 38, counts: { low: 1, medium: 0, high: 0, critical: 0 } });
    expect(short.riskIndex).toBeNull();
    expect(short.score).toBeNull();
  });

  it("ranks riskiest drivers first and unscored drivers last", () => {
    const ranking = driverRanking();
    const scored = ranking.filter((d) => d.riskIndex !== null).map((d) => d.riskIndex ?? 0);
    expect(scored).toEqual([...scored].sort((a, b) => b - a));
    expect(ranking.at(-1)?.riskIndex).toBeNull();
    expect(averageRiskIndex()).toBeGreaterThan(0);
  });

  it("formats relative times and rule explanations in Turkish", () => {
    expect(relativeMinutes(6)).toBe("6 dk önce");
    expect(relativeMinutes(120)).toBe("2 sa önce");
    expect(relativeMinutes(126)).toBe("2 sa 6 dk önce");
    expect(explainEvent(DEMO_EVENTS[0]!)).toBe("Ölçülen 6,1 m/s², eşik 3,5 m/s².");
    expect(explainEvent(DEMO_EVENTS.find((e) => e.type === "gps_anomaly")!)).toContain("insan incelemesine");
  });
});
