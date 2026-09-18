/**
 * Deterministic synthetic fixtures for the public /demo showcase.
 *
 * Nothing here comes from the API or from any tenant: the public demo never
 * calls a private endpoint. Every vehicle, driver, plate, position and event is
 * invented (plates use the fictional "DMO" series, drivers are pseudonymous
 * codes) and the whole data set carries data_origin="synthetic" /
 * environment="demo", mirroring the backend's data-origin rules.
 *
 * Rule thresholds and the driver score formula mirror the backend defaults
 * (visionroute.domain.safety.Thresholds, visionroute.domain.driver_score) so
 * the preview explains the product honestly. Timestamps are relative minutes,
 * not wall-clock dates, so server and client render identically.
 */

export const DEMO_DATA_ORIGIN = "synthetic" as const;
export const DEMO_ENVIRONMENT = "demo" as const;
export const DEMO_ORGANIZATION = "Demo Lojistik (kurgusal)";

export type DemoSeverity = "low" | "medium" | "high" | "critical";
export type DemoEventType =
  | "harsh_braking"
  | "harsh_acceleration"
  | "harsh_cornering"
  | "speeding"
  | "gps_anomaly";

export const DEMO_SEVERITIES: DemoSeverity[] = ["low", "medium", "high", "critical"];

export const DEMO_EVENT_LABELS: Record<DemoEventType, string> = {
  harsh_braking: "Sert fren",
  harsh_acceleration: "Sert hızlanma",
  harsh_cornering: "Sert viraj",
  speeding: "Hız aşımı",
  gps_anomaly: "GPS anomalisi",
};

/** Backend default thresholds (visionroute.domain.safety.Thresholds). */
export const DEMO_THRESHOLDS: Record<Exclude<DemoEventType, "gps_anomaly">, { value: number; unit: string }> = {
  harsh_braking: { value: 3.5, unit: "m/s²" },
  harsh_acceleration: { value: 3.0, unit: "m/s²" },
  harsh_cornering: { value: 4.0, unit: "m/s²" },
  speeding: { value: 120, unit: "km/sa" },
};

/** visionroute.domain.driver_score.SEVERITY_WEIGHTS */
export const SEVERITY_WEIGHTS: Record<DemoSeverity, number> = {
  low: 1.0,
  medium: 2.5,
  high: 5.0,
  critical: 9.0,
};

/** visionroute.domain.driver_score.MIN_EXPOSURE_KM */
export const MIN_EXPOSURE_KM = 50;

export interface DemoVehicle {
  id: string;
  plate: string;
  driver: string;
  latitude: number;
  longitude: number;
  speedKph: number;
  area: string;
  stale: boolean;
}

export interface DemoEvent {
  id: string;
  type: DemoEventType;
  severity: DemoSeverity;
  vehicle: string;
  driver: string;
  place: string;
  latitude: number;
  longitude: number;
  minutesAgo: number;
  /** Measured value in the rule's unit; null for GPS anomalies. */
  measured: number | null;
  confidence: number;
  review: "pending" | "confirmed" | "uncertain";
  hasEvidence: boolean;
}

export interface DemoDriver {
  code: string;
  exposureKm: number;
  counts: Record<DemoSeverity, number>;
}

export interface DemoRoadRisk {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  radiusM: number;
  severity: DemoSeverity;
  eventCount: number;
  dominant: DemoEventType;
}

export const DEMO_VEHICLE_TOTAL = 18;
export const DEMO_DRIVER_TOTAL = 16;

export const DEMO_VEHICLES: DemoVehicle[] = [
  { id: "demo-v-01", plate: "34 DMO 118", driver: "Sürücü D-07", latitude: 41.0712, longitude: 29.2604, speedKph: 74, area: "TEM · Çekmeköy", stale: false },
  { id: "demo-v-02", plate: "34 DMO 142", driver: "Sürücü D-01", latitude: 40.9861, longitude: 28.7214, speedKph: 58, area: "D-100 · Avcılar", stale: false },
  { id: "demo-v-03", plate: "41 DMO 207", driver: "Sürücü D-12", latitude: 40.7803, longitude: 29.5612, speedKph: 86, area: "O-4 · Dilovası", stale: false },
  { id: "demo-v-04", plate: "41 DMO 233", driver: "Sürücü D-09", latitude: 40.7652, longitude: 29.9407, speedKph: 0, area: "İzmit depo", stale: false },
  { id: "demo-v-05", plate: "16 DMO 310", driver: "Sürücü D-03", latitude: 40.2311, longitude: 28.9302, speedKph: 63, area: "Bursa çevre yolu", stale: false },
  { id: "demo-v-06", plate: "54 DMO 402", driver: "Sürücü D-15", latitude: 40.7702, longitude: 30.6104, speedKph: 92, area: "O-4 · Akyazı", stale: false },
  { id: "demo-v-07", plate: "14 DMO 415", driver: "Sürücü D-11", latitude: 40.7398, longitude: 31.7911, speedKph: 67, area: "O-4 · Bolu", stale: false },
  { id: "demo-v-08", plate: "06 DMO 204", driver: "Sürücü D-05", latitude: 39.9057, longitude: 32.7611, speedKph: 81, area: "Eskişehir yolu", stale: false },
  { id: "demo-v-09", plate: "06 DMO 219", driver: "Sürücü D-02", latitude: 40.1203, longitude: 32.9902, speedKph: 96, area: "Esenboğa yolu", stale: false },
  { id: "demo-v-10", plate: "71 DMO 505", driver: "Sürücü D-04", latitude: 39.8102, longitude: 33.7004, speedKph: 88, area: "Kırıkkale çıkışı", stale: false },
  { id: "demo-v-11", plate: "26 DMO 611", driver: "Sürücü D-06", latitude: 39.7804, longitude: 30.5209, speedKph: 44, area: "Eskişehir", stale: false },
  { id: "demo-v-12", plate: "03 DMO 702", driver: "Sürücü D-08", latitude: 38.7612, longitude: 30.5405, speedKph: 79, area: "Afyonkarahisar", stale: false },
  { id: "demo-v-13", plate: "35 DMO 801", driver: "Sürücü D-10", latitude: 38.5104, longitude: 27.3301, speedKph: 52, area: "İzmir–Manisa yolu", stale: false },
  { id: "demo-v-14", plate: "45 DMO 822", driver: "Sürücü D-13", latitude: 38.6195, longitude: 27.4302, speedKph: 0, area: "Manisa", stale: true },
];

export const DEMO_EVENTS: DemoEvent[] = [
  { id: "demo-e-01", type: "harsh_braking", severity: "high", vehicle: "34 DMO 118", driver: "Sürücü D-07", place: "TEM · Kavacık bağlantısı", latitude: 41.0882, longitude: 29.0865, minutesAgo: 6, measured: 6.1, confidence: 0.94, review: "pending", hasEvidence: true },
  { id: "demo-e-02", type: "speeding", severity: "critical", vehicle: "06 DMO 219", driver: "Sürücü D-02", place: "Esenboğa yolu", latitude: 40.0215, longitude: 32.9211, minutesAgo: 14, measured: 146, confidence: 0.97, review: "pending", hasEvidence: false },
  { id: "demo-e-03", type: "harsh_cornering", severity: "medium", vehicle: "14 DMO 415", driver: "Sürücü D-11", place: "O-4 · Bolu Dağı geçişi", latitude: 40.7581, longitude: 31.5874, minutesAgo: 23, measured: 5.3, confidence: 0.88, review: "pending", hasEvidence: true },
  { id: "demo-e-04", type: "speeding", severity: "medium", vehicle: "54 DMO 402", driver: "Sürücü D-15", place: "O-4 · Sakarya", latitude: 40.7412, longitude: 30.3605, minutesAgo: 31, measured: 131, confidence: 0.95, review: "confirmed", hasEvidence: false },
  { id: "demo-e-05", type: "harsh_acceleration", severity: "low", vehicle: "16 DMO 310", driver: "Sürücü D-03", place: "Bursa çevre yolu", latitude: 40.1987, longitude: 29.0712, minutesAgo: 44, measured: 3.4, confidence: 0.91, review: "confirmed", hasEvidence: false },
  { id: "demo-e-06", type: "gps_anomaly", severity: "low", vehicle: "45 DMO 822", driver: "Sürücü D-13", place: "Manisa", latitude: 38.6602, longitude: 27.3401, minutesAgo: 52, measured: null, confidence: 0.41, review: "uncertain", hasEvidence: false },
  { id: "demo-e-07", type: "harsh_braking", severity: "medium", vehicle: "41 DMO 207", driver: "Sürücü D-12", place: "D-100 · Gebze kavşağı", latitude: 40.7976, longitude: 29.4402, minutesAgo: 67, measured: 4.8, confidence: 0.9, review: "confirmed", hasEvidence: true },
  { id: "demo-e-08", type: "harsh_braking", severity: "high", vehicle: "34 DMO 118", driver: "Sürücü D-07", place: "TEM · Kavacık bağlantısı", latitude: 41.0891, longitude: 29.0878, minutesAgo: 88, measured: 6.4, confidence: 0.93, review: "confirmed", hasEvidence: true },
  { id: "demo-e-09", type: "harsh_cornering", severity: "low", vehicle: "35 DMO 801", driver: "Sürücü D-10", place: "İzmir · Bornova", latitude: 38.4623, longitude: 27.2159, minutesAgo: 103, measured: 4.3, confidence: 0.86, review: "pending", hasEvidence: false },
  { id: "demo-e-10", type: "speeding", severity: "high", vehicle: "71 DMO 505", driver: "Sürücü D-04", place: "Kırıkkale", latitude: 39.8522, longitude: 33.4987, minutesAgo: 126, measured: 139, confidence: 0.96, review: "pending", hasEvidence: false },
];

/** Safety events in the last 24 hours, by severity. */
export const DEMO_SEVERITY_COUNTS_24H: Record<DemoSeverity, number> = {
  low: 64,
  medium: 41,
  high: 18,
  critical: 3,
};

/** Same 24-hour window, by rule. */
export const DEMO_TYPE_COUNTS_24H: Record<DemoEventType, number> = {
  harsh_braking: 47,
  speeding: 38,
  harsh_cornering: 21,
  harsh_acceleration: 14,
  gps_anomaly: 6,
};

/** Same 24-hour window, by hour of day (00:00 → 23:00, Europe/Istanbul). */
export const DEMO_HOURLY_EVENTS_24H: number[] = [
  1, 1, 0, 1, 1, 2, 4, 8, 11, 9, 7, 6, 6, 7, 6, 7, 9, 11, 10, 7, 5, 4, 2, 1,
];

export const DEMO_PENDING_REVIEW = 23;

export const DEMO_TRIPS_24H = {
  completed: 87,
  ongoing: DEMO_VEHICLES.filter((v) => !v.stale && v.speedKph > 0).length,
  distanceKm: 6420,
  drivingHours: 312,
  openCoaching: 9,
};

/** Seven-day exposure and event counts per driver. */
export const DEMO_DRIVERS: DemoDriver[] = [
  { code: "Sürücü D-07", exposureKm: 1240, counts: { low: 10, medium: 7, high: 5, critical: 1 } },
  { code: "Sürücü D-12", exposureKm: 1610, counts: { low: 12, medium: 6, high: 3, critical: 1 } },
  { code: "Sürücü D-03", exposureKm: 980, counts: { low: 6, medium: 4, high: 2, critical: 0 } },
  { code: "Sürücü D-15", exposureKm: 1420, counts: { low: 8, medium: 3, high: 2, critical: 0 } },
  { code: "Sürücü D-01", exposureKm: 1760, counts: { low: 9, medium: 3, high: 1, critical: 0 } },
  { code: "Sürücü D-09", exposureKm: 1105, counts: { low: 5, medium: 2, high: 0, critical: 0 } },
  { code: "Sürücü D-11", exposureKm: 1530, counts: { low: 4, medium: 1, high: 0, critical: 0 } },
  { code: "Sürücü D-05", exposureKm: 890, counts: { low: 2, medium: 0, high: 0, critical: 0 } },
  { code: "Sürücü D-16", exposureKm: 38, counts: { low: 1, medium: 0, high: 0, critical: 0 } },
];

export const DEMO_ROAD_RISKS: DemoRoadRisk[] = [
  { id: "demo-r-01", name: "TEM · Kavacık bağlantısı", latitude: 41.0887, longitude: 29.0871, radiusM: 900, severity: "high", eventCount: 14, dominant: "harsh_braking" },
  { id: "demo-r-02", name: "O-4 · Bolu Dağı geçişi", latitude: 40.7578, longitude: 31.5901, radiusM: 1600, severity: "high", eventCount: 11, dominant: "harsh_cornering" },
  { id: "demo-r-03", name: "D-100 · Gebze kavşağı", latitude: 40.7981, longitude: 29.4395, radiusM: 1100, severity: "medium", eventCount: 8, dominant: "harsh_braking" },
  { id: "demo-r-04", name: "Esenboğa yolu", latitude: 40.0198, longitude: 32.9187, radiusM: 1400, severity: "medium", eventCount: 6, dominant: "speeding" },
];

export interface DriverRisk {
  code: string;
  exposureKm: number;
  eventCount: number;
  weightedEvents: number;
  /** Weighted events per 100 km (lower is safer); null below minimum exposure. */
  riskIndex: number | null;
  /** 0 (worst) .. 100 (best); null below minimum exposure. */
  score: number | null;
}

/**
 * Same shape as visionroute.domain.driver_score.compute_driver_score for
 * confirmed, same-day events (no recency decay, full confidence).
 */
export function driverRisk(driver: DemoDriver): DriverRisk {
  const eventCount = DEMO_SEVERITIES.reduce((sum, s) => sum + driver.counts[s], 0);
  const weightedEvents = DEMO_SEVERITIES.reduce((sum, s) => sum + driver.counts[s] * SEVERITY_WEIGHTS[s], 0);
  if (driver.exposureKm < MIN_EXPOSURE_KM) {
    return { code: driver.code, exposureKm: driver.exposureKm, eventCount, weightedEvents, riskIndex: null, score: null };
  }
  const riskIndex = weightedEvents / (driver.exposureKm / 100);
  const score = 100 * Math.exp(-riskIndex / 14.43);
  return { code: driver.code, exposureKm: driver.exposureKm, eventCount, weightedEvents, riskIndex, score };
}

/** Drivers ordered riskiest first; drivers without enough exposure last. */
export function driverRanking(drivers: DemoDriver[] = DEMO_DRIVERS): DriverRisk[] {
  return drivers
    .map(driverRisk)
    .sort((a, b) => (b.riskIndex ?? -1) - (a.riskIndex ?? -1));
}

export function averageRiskIndex(drivers: DemoDriver[] = DEMO_DRIVERS): number {
  const scored = drivers.map(driverRisk).filter((d) => d.riskIndex !== null);
  if (scored.length === 0) return 0;
  return scored.reduce((sum, d) => sum + (d.riskIndex ?? 0), 0) / scored.length;
}

export function totalEvents24h(): number {
  return DEMO_SEVERITIES.reduce((sum, s) => sum + DEMO_SEVERITY_COUNTS_24H[s], 0);
}

export function eventsPer100Km(): number {
  return totalEvents24h() / (DEMO_TRIPS_24H.distanceKm / 100);
}

export function activeVehicleCount(): number {
  return DEMO_VEHICLES.filter((v) => !v.stale).length;
}

export function activeDriverCount(): number {
  return new Set(DEMO_VEHICLES.filter((v) => !v.stale).map((v) => v.driver)).size;
}

/** "12 dk önce" / "2 sa 6 dk önce" — relative to the fixed demo moment. */
export function relativeMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} dk önce`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} sa önce` : `${hours} sa ${rest} dk önce`;
}

/** Plain-language rule explanation, as the real event detail shows it. */
export function explainEvent(event: DemoEvent): string {
  if (event.type === "gps_anomaly" || event.measured === null) {
    return "Konum sıçraması ve düşük uydu sayısı nedeniyle veri kalitesi düşük; olay otomatik puanlanmadı, insan incelemesine işaretlendi.";
  }
  const rule = DEMO_THRESHOLDS[event.type];
  const measured = event.measured.toLocaleString("tr-TR", { maximumFractionDigits: 1 });
  const threshold = rule.value.toLocaleString("tr-TR", { maximumFractionDigits: 1 });
  return `Ölçülen ${measured} ${rule.unit}, eşik ${threshold} ${rule.unit}.`;
}
