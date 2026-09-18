// MapLibre GL 6 locates its web worker relative to import.meta.url, which the
// Next.js bundler rewrites, so the worker 404s and GeoJSON layers (vehicles,
// events, risk areas) never render. Serve the worker and the shared module it
// imports as static files from the installed package, so they always match
// the bundled version; FleetMap points maplibregl.setWorkerUrl() at them.
import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "node_modules/maplibre-gl/dist");
const target = path.join(root, "public/maplibre");
const { version } = JSON.parse(readFileSync(path.join(root, "node_modules/maplibre-gl/package.json"), "utf8"));

mkdirSync(target, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(path.join(dist, file), path.join(target, file));
}
console.log(`maplibre-gl ${version} worker -> public/maplibre`);
