import path from "node:path";

export const API_PORT = 8100;
export const WEB_PORT = 3100;
export const WORKER_METRICS_PORT = 9110;
export const API_URL = `http://localhost:${API_PORT}`;
export const WEB_URL = `http://localhost:${WEB_PORT}`;
export const E2E_DIR = path.resolve(__dirname, "../../../../.localdata/e2e");
export const MAIL_DIR = path.join(E2E_DIR, "mail");

export const PASSWORD = "E2eGuvenliParola42!";
export const NEW_PASSWORD = "E2eYeniParola77!";

export function unique(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
}
