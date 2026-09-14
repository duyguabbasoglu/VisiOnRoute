import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { API_URL, PASSWORD, unique } from "./env";
import { oneTimeLink, waitForEmail } from "./mail";

export interface Account {
  slug: string;
  email: string;
  password: string;
  orgName: string;
  fullName: string;
}

export function newAccount(prefix: string): Account {
  const slug = unique(prefix).toLowerCase();
  return {
    slug,
    email: `${slug}@ornek.example`,
    password: PASSWORD,
    orgName: `E2E Filo ${slug}`,
    fullName: "Deniz Yılmaz",
  };
}

export async function register(page: Page, account: Account): Promise<void> {
  await page.goto("/kayit");
  await page.getByLabel("Organizasyon adı").fill(account.orgName);
  await page.getByLabel("Kısa ad").fill(account.slug);
  await page.getByLabel("Ad soyad").fill(account.fullName);
  await page.getByLabel("E-posta").fill(account.email);
  await page.getByLabel("Parola", { exact: true }).fill(account.password);
  await page.getByLabel("Parola (tekrar)").fill(account.password);
  await page.getByRole("button", { name: "Hesap oluştur" }).click();
  await expect(page).toHaveURL(/\/panel$/);
  await expect(page.getByRole("heading", { name: "Genel Bakış" })).toBeVisible();
}

export async function verifyEmail(page: Page, account: Account): Promise<void> {
  const email = await waitForEmail(account.email, "/eposta-dogrula");
  await page.goto(oneTimeLink(email, "/eposta-dogrula"));
  await expect(page.getByText("E-posta adresiniz doğrulandı. Teşekkürler!")).toBeVisible();
}

export async function login(page: Page, email: string, password: string): Promise<void> {
  if (!page.url().includes("/giris")) await page.goto("/giris");
  await page.getByLabel("E-posta").fill(email);
  await page.getByLabel("Parola", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Giriş yap" }).click();
}

export async function logout(page: Page): Promise<void> {
  // The shell offers logout in both the sidebar and the header.
  await page.getByRole("button", { name: "Çıkış yap" }).first().click();
  await expect(page).toHaveURL(/\/giris/);
}

export async function apiAccessToken(request: APIRequestContext, email: string, password: string): Promise<string> {
  const response = await request.post(`${API_URL}/api/v1/auth/login`, { data: { email, password } });
  expect(response.ok(), await response.text()).toBeTruthy();
  const body = (await response.json()) as { access_token?: string };
  if (!body.access_token) throw new Error("access_token yok (MFA etkin olabilir)");
  return body.access_token;
}

export function bearer(token: string): { headers: Record<string, string> } {
  return { headers: { Authorization: `Bearer ${token}` } };
}

/** One harsh-braking telemetry point (the deterministic rule engine turns it into an event). */
export async function ingestHarshBraking(
  request: APIRequestContext,
  apiKey: string,
  sourceKey: string,
  vehicleExternalId: string,
): Promise<void> {
  const response = await request.post(`${API_URL}/api/v1/ingest/events`, {
    headers: { "X-API-Key": apiKey },
    data: {
      source_key: sourceKey,
      events: [
        {
          schema_version: "1.0",
          source: sourceKey,
          event_id: unique("fren"),
          event_type: "telemetry.position",
          occurred_at: new Date(Date.now() - 2 * 60_000).toISOString(),
          vehicle_external_id: vehicleExternalId,
          payload: {
            latitude: 39.92,
            longitude: 32.85,
            speed_kph: 70,
            acceleration_ms2: -6.5,
            gps_hdop: 1.0,
            satellites: 12,
          },
        },
      ],
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  expect(((await response.json()) as { accepted: number }).accepted).toBe(1);
}

export async function waitForFirstEvent(request: APIRequestContext, token: string): Promise<string> {
  let eventId = "";
  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_URL}/api/v1/safety-events`, bearer(token));
        const body = (await response.json()) as { items: { id: string }[] };
        eventId = body.items[0]?.id ?? "";
        return eventId;
      },
      { timeout: 30_000, message: "Worker güvenlik olayını üretmedi" },
    )
    .not.toBe("");
  return eventId;
}

/** Tenant fixture through the public API: vehicle, data source, ingest key, one event. */
export async function seedEventViaApi(request: APIRequestContext, token: string): Promise<string> {
  const auth = bearer(token);
  const vehicle = unique("34API").toUpperCase();
  const sourceKey = unique("kaynak").toLowerCase();
  expect((await request.post(`${API_URL}/api/v1/vehicles`, { ...auth, data: { external_id: vehicle } })).ok()).toBeTruthy();
  expect(
    (
      await request.post(`${API_URL}/api/v1/integrations/data-sources`, {
        ...auth,
        data: { name: "API kaynağı", source_key: sourceKey, kind: "rest" },
      })
    ).ok(),
  ).toBeTruthy();
  const client = (await (
    await request.post(`${API_URL}/api/v1/integrations/clients`, { ...auth, data: { name: "E2E cihaz" } })
  ).json()) as { id: string };
  const issued = (await (
    await request.post(`${API_URL}/api/v1/integrations/clients/${client.id}/tokens`, {
      ...auth,
      data: { scopes: ["ingest:write"] },
    })
  ).json()) as { api_key: string };
  await ingestHarshBraking(request, issued.api_key, sourceKey, vehicle);
  return waitForFirstEvent(request, token);
}
