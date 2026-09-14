import { readFileSync } from "node:fs";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";
import { API_URL, E2E_DIR, WEB_PORT, WEB_URL, WORKER_METRICS_PORT } from "./e2e/support/env";

const ROOT = path.resolve(__dirname, "../..");

function secret(name: string): string {
  try {
    return readFileSync(path.join(E2E_DIR, name), "utf8").trim();
  } catch {
    return "";
  }
}

const pg = {
  host: process.env.E2E_PGHOST ?? "localhost",
  port: process.env.E2E_PGPORT ?? "5433",
  user: process.env.E2E_PGUSER ?? "visionroute",
  password: process.env.E2E_PGPASSWORD ?? "visionroute",
  database: process.env.E2E_DB ?? "visionroute_e2e",
};

// Same code paths as production (file mail backend and local object storage
// stand in for SMTP and S3); generous rate limits because every browser
// session shares one client address.
const backendEnv: Record<string, string> = {
  ...(process.env as Record<string, string>),
  VISIONROUTE_DISABLE_DOTENV: "1",
  VISIONROUTE_DATABASE_URL: `postgresql+asyncpg://${pg.user}:${pg.password}@${pg.host}:${pg.port}/${pg.database}`,
  VISIONROUTE_JWT_PRIVATE_KEY_PATH: path.join(E2E_DIR, "keys/jwt-private.pem"),
  VISIONROUTE_JWT_PUBLIC_KEY_PATH: path.join(E2E_DIR, "keys/jwt-public.pem"),
  VISIONROUTE_FIELD_ENCRYPTION_KEYS: JSON.stringify({ e2e1: secret("field-key") }),
  VISIONROUTE_FIELD_ENCRYPTION_PRIMARY_KEY_ID: "e2e1",
  VISIONROUTE_MAIL_BACKEND: "file",
  VISIONROUTE_MAIL_FILE_DIR: path.join(E2E_DIR, "mail"),
  VISIONROUTE_STORAGE_BACKEND: "local",
  VISIONROUTE_LOCAL_STORAGE_DIR: path.join(E2E_DIR, "objects"),
  VISIONROUTE_LOCAL_STORAGE_SIGNING_KEY: secret("storage-key"),
  VISIONROUTE_PUBLIC_API_URL: API_URL,
  VISIONROUTE_PUBLIC_APP_URL: WEB_URL,
  VISIONROUTE_CORS_ORIGINS: JSON.stringify([WEB_URL]),
  VISIONROUTE_LOGIN_RATE_LIMIT_PER_MINUTE: "1000",
  VISIONROUTE_LOGIN_IP_RATE_LIMIT_PER_MINUTE: "10000",
  VISIONROUTE_REGISTER_RATE_LIMIT_PER_HOUR: "1000",
  VISIONROUTE_TOKEN_RATE_LIMIT_PER_MINUTE: "10000",
  VISIONROUTE_ACCOUNT_EMAIL_RATE_LIMIT_PER_HOUR: "1000",
};

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  // Flows share one database and a single worker process; run them serially.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: WEB_URL,
    locale: "tr-TR",
    timezoneId: "Europe/Istanbul",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `poetry run uvicorn visionroute.api.main:create_app --factory --host 127.0.0.1 --port ${new URL(API_URL).port}`,
      cwd: ROOT,
      env: backendEnv,
      url: `${API_URL}/health/ready`,
      reuseExistingServer: false,
      timeout: 90_000,
    },
    {
      command: `poetry run visionroute worker run --poll-interval 0.5 --metrics-port ${WORKER_METRICS_PORT}`,
      cwd: ROOT,
      env: backendEnv,
      url: `http://127.0.0.1:${WORKER_METRICS_PORT}/`,
      reuseExistingServer: false,
      timeout: 90_000,
    },
    {
      command: `pnpm build && pnpm start --hostname 127.0.0.1 --port ${WEB_PORT}`,
      cwd: __dirname,
      env: { ...(process.env as Record<string, string>), NEXT_PUBLIC_API_URL: API_URL },
      url: `${WEB_URL}/giris`,
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
});
