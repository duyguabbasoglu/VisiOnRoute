"use client";

/**
 * Operational map (MapLibre GL + OpenStreetMap raster tiles, no API key).
 *
 * Only real coordinates reported by the API are drawn; nothing is invented.
 * Popups are built with DOM text nodes (never HTML strings), and every map is
 * paired with a list/table elsewhere on the page so the data stays accessible
 * without a pointer or WebGL.
 */
import "maplibre-gl/dist/maplibre-gl.css";
import type { GeoJSONSource, Map as MapLibreMap, MapLayerMouseEvent, Popup } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

export interface MapPoint {
  id: string;
  latitude: number;
  longitude: number;
  label: string;
  detail?: string;
}

export interface MapVehicle extends MapPoint {
  stale: boolean;
}

export interface MapEvent extends MapPoint {
  severity: string;
}

export interface MapArea extends MapPoint {
  radiusM: number;
  severity?: string;
}

export interface FleetMapData {
  vehicles?: MapVehicle[];
  events?: MapEvent[];
  risks?: MapArea[];
  geofences?: MapArea[];
  /** Ordered [longitude, latitude] pairs of a trip trail. */
  trail?: [number, number][];
}

export type MapSelection = { kind: "vehicle" | "event" | "risk" | "geofence"; id: string };

const MAPLIBRE_WORKER_URL = "/maplibre/maplibre-gl-worker.mjs";

const TURKEY_CENTER: [number, number] = [35.2, 39.0];

const SEVERITY_COLORS: Record<string, string> = {
  low: "#16a34a",
  medium: "#d97706",
  high: "#ea580c",
  critical: "#b91c1c",
};

const TILE_STYLE = {
  version: 8 as const,
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> katkıda bulunanlar',
    },
  },
  layers: [{ id: "osm", type: "raster" as const, source: "osm" }],
};

type Geometry =
  | { type: "Point"; coordinates: [number, number] }
  | { type: "LineString"; coordinates: [number, number][] }
  | { type: "Polygon"; coordinates: [number, number][][] };
type Feature = { type: "Feature"; geometry: Geometry; properties: Record<string, string | number | boolean> };
type FeatureCollection = { type: "FeatureCollection"; features: Feature[] };

function collection(features: Feature[]): FeatureCollection {
  return { type: "FeatureCollection", features };
}

function pointFeature(kind: MapSelection["kind"], p: MapPoint, extra: Record<string, string | number | boolean> = {}): Feature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [p.longitude, p.latitude] },
    properties: { kind, id: p.id, label: p.label, detail: p.detail ?? "", ...extra },
  };
}

/** Circle of ``radiusM`` metres approximated by a 48-vertex polygon. */
function circleFeature(kind: MapSelection["kind"], area: MapArea, color: string): Feature {
  const steps = 48;
  const earth = 6_371_000;
  const lat = (area.latitude * Math.PI) / 180;
  const ring: [number, number][] = [];
  for (let i = 0; i <= steps; i += 1) {
    const bearing = (2 * Math.PI * i) / steps;
    const dLat = (area.radiusM / earth) * Math.cos(bearing);
    const dLon = (area.radiusM / earth) * (Math.sin(bearing) / Math.cos(lat));
    ring.push([area.longitude + (dLon * 180) / Math.PI, area.latitude + (dLat * 180) / Math.PI]);
  }
  return {
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [ring] },
    properties: { kind, id: area.id, label: area.label, detail: area.detail ?? "", color },
  };
}

function buildSources(data: FleetMapData) {
  return {
    trail: collection(
      data.trail && data.trail.length > 1
        ? [{ type: "Feature", geometry: { type: "LineString", coordinates: data.trail }, properties: {} }]
        : [],
    ),
    areas: collection([
      ...(data.geofences ?? []).map((g) => circleFeature("geofence", g, "#2563eb")),
      ...(data.risks ?? []).map((r) => circleFeature("risk", r, SEVERITY_COLORS[r.severity ?? "medium"] ?? "#d97706")),
    ]),
    events: collection(
      (data.events ?? []).map((e) => pointFeature("event", e, { color: SEVERITY_COLORS[e.severity] ?? "#64748b" })),
    ),
    vehicles: collection((data.vehicles ?? []).map((v) => pointFeature("vehicle", v, { stale: v.stale }))),
  };
}

function allCoordinates(data: FleetMapData): [number, number][] {
  const points: [number, number][] = [];
  for (const list of [data.vehicles, data.events, data.risks, data.geofences]) {
    for (const p of list ?? []) points.push([p.longitude, p.latitude]);
  }
  for (const c of data.trail ?? []) points.push(c);
  return points;
}

export function FleetMap({
  data,
  label,
  onSelect,
  onPick,
  className = "h-[28rem]",
}: {
  data: FleetMapData;
  label: string;
  onSelect?: (selection: MapSelection) => void;
  /** Called with the clicked coordinate when the click hits no feature. */
  onPick?: (latitude: number, longitude: number) => void;
  className?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const popupRef = useRef<Popup | null>(null);
  const loadedRef = useRef(false);
  const fittedRef = useRef(false);
  const dataRef = useRef(data);
  const onSelectRef = useRef(onSelect);
  const onPickRef = useRef(onPick);
  const [failed, setFailed] = useState(false);

  dataRef.current = data;
  onSelectRef.current = onSelect;
  onPickRef.current = onPick;

  useEffect(() => {
    let disposed = false;
    void (async () => {
      const probe = document.createElement("canvas");
      if (!probe.getContext("webgl2") && !probe.getContext("webgl")) {
        setFailed(true);
        return;
      }
      const maplibregl = await import("maplibre-gl");
      if (disposed || !container.current) return;
      // Bundling breaks MapLibre's import.meta.url worker lookup; the build
      // copies the matching worker to public/maplibre (scripts/copy-maplibre-worker.mjs).
      maplibregl.setWorkerUrl(MAPLIBRE_WORKER_URL);
      let map: MapLibreMap;
      try {
        map = new maplibregl.Map({
          container: container.current,
          style: TILE_STYLE,
          center: TURKEY_CENTER,
          zoom: 5,
          attributionControl: { compact: true },
        });
      } catch {
        setFailed(true);
        return;
      }
      mapRef.current = map;
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("error", () => undefined);
      map.on("load", () => {
        const sources = buildSources(dataRef.current);
        map.addSource("trail", { type: "geojson", data: sources.trail });
        map.addSource("areas", { type: "geojson", data: sources.areas });
        map.addSource("events", { type: "geojson", data: sources.events });
        map.addSource("vehicles", { type: "geojson", data: sources.vehicles });
        map.addLayer({
          id: "areas-fill",
          type: "fill",
          source: "areas",
          paint: { "fill-color": ["get", "color"], "fill-opacity": 0.18 },
        });
        map.addLayer({
          id: "areas-line",
          type: "line",
          source: "areas",
          paint: { "line-color": ["get", "color"], "line-width": 1.5 },
        });
        map.addLayer({
          id: "trail-line",
          type: "line",
          source: "trail",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": "#1d4ed8", "line-width": 4, "line-opacity": 0.85 },
        });
        map.addLayer({
          id: "events-circle",
          type: "circle",
          source: "events",
          paint: {
            "circle-radius": 7,
            "circle-color": ["get", "color"],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
          },
        });
        map.addLayer({
          id: "vehicles-circle",
          type: "circle",
          source: "vehicles",
          paint: {
            "circle-radius": 9,
            "circle-color": ["case", ["get", "stale"], "#94a3b8", "#0b1220"],
            "circle-stroke-color": "#60a5fa",
            "circle-stroke-width": 3,
          },
        });
        loadedRef.current = true;
        fit(map, dataRef.current);

        const interactive = ["vehicles-circle", "events-circle", "areas-fill"];
        for (const layer of interactive) {
          map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
          map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
        }
        map.on("click", (event: MapLayerMouseEvent) => {
          const [feature] = map.queryRenderedFeatures(event.point, { layers: interactive });
          popupRef.current?.remove();
          if (!feature) {
            onPickRef.current?.(event.lngLat.lat, event.lngLat.lng);
            return;
          }
          const props = feature.properties as Record<string, string>;
          const body = document.createElement("div");
          body.className = "text-sm";
          const title = document.createElement("p");
          title.className = "font-medium text-ink-900";
          title.textContent = props.label ?? "";
          body.appendChild(title);
          if (props.detail) {
            const detail = document.createElement("p");
            detail.className = "mt-0.5 text-xs text-slate-500";
            detail.textContent = props.detail;
            body.appendChild(detail);
          }
          const handler = onSelectRef.current;
          const kind = props.kind as MapSelection["kind"];
          if (handler && (kind === "vehicle" || kind === "event")) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "mt-2 text-xs font-medium text-brand-700 underline";
            button.textContent = kind === "event" ? "Olayı incele" : "Seferi aç";
            button.addEventListener("click", () => handler({ kind, id: props.id ?? "" }));
            body.appendChild(button);
          }
          popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: "260px" })
            .setLngLat(event.lngLat)
            .setDOMContent(body)
            .addTo(map);
        });
      });
    })();
    return () => {
      disposed = true;
      popupRef.current?.remove();
      mapRef.current?.remove();
      mapRef.current = null;
      loadedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    const sources = buildSources(data);
    for (const name of ["trail", "areas", "events", "vehicles"] as const) {
      (map.getSource(name) as GeoJSONSource | undefined)?.setData(sources[name]);
    }
    if (!fittedRef.current) fit(map, data);
  }, [data]);

  function fit(map: MapLibreMap, current: FleetMapData) {
    const coordinates = allCoordinates(current);
    const first = coordinates[0];
    if (!first) return;
    fittedRef.current = true;
    if (coordinates.length === 1) {
      map.jumpTo({ center: first, zoom: 14 });
      return;
    }
    let [minLon, minLat] = first;
    let [maxLon, maxLat] = first;
    for (const [lon, lat] of coordinates) {
      minLon = Math.min(minLon, lon);
      maxLon = Math.max(maxLon, lon);
      minLat = Math.min(minLat, lat);
      maxLat = Math.max(maxLat, lat);
    }
    map.fitBounds(
      [
        [minLon, minLat],
        [maxLon, maxLat],
      ],
      { padding: 48, maxZoom: 15, duration: 0 },
    );
  }

  const empty = allCoordinates(data).length === 0;

  return (
    <div className={`relative overflow-hidden rounded-xl border border-slate-200 bg-slate-100 ${className}`}>
      {/* MapLibre styles its container as position:relative, so size it explicitly. */}
      <div ref={container} role="region" aria-label={label} className="h-full w-full" />
      {failed && (
        <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-slate-600">
          Harita bu tarayıcıda görüntülenemiyor (WebGL gerekli). Aynı veriler sayfadaki listede yer alır.
        </div>
      )}
      {!failed && empty && (
        <div className="pointer-events-none absolute inset-x-0 top-3 flex justify-center">
          <span className="rounded-full bg-white/95 px-3 py-1 text-xs text-slate-600 shadow">
            Gösterilecek konum verisi yok
          </span>
        </div>
      )}
    </div>
  );
}

export const MAP_SEVERITY_COLORS = SEVERITY_COLORS;
