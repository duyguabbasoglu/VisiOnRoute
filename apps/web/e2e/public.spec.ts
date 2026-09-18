import { expect, test, type Page } from "@playwright/test";
import { newAccount, register } from "./support/flows";

/** Every API path the page requested, except the session probe every page makes. */
function trackApiCalls(page: Page): string[] {
  const calls: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/") && url.pathname !== "/api/v1/auth/refresh") calls.push(url.pathname);
  });
  return calls;
}

test("anonim ziyaretçi ana sayfada ürün tanıtımını görür, girişe yönlendirilmez", async ({ page }) => {
  const apiCalls = trackApiCalls(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("VISiOnRoute");
  await expect(page.getByText("Hobi demo · yalnızca sentetik veri").first()).toBeVisible();
  const main = page.getByRole("main");
  await expect(main.getByRole("link", { name: /Demoyu keşfet/ }).first()).toBeVisible();
  await expect(main.getByRole("link", { name: "Giriş yap" })).toBeVisible();
  await expect(main.getByRole("link", { name: "Yeni organizasyon oluştur" }).first()).toBeVisible();
  for (const capability of ["Gerçek zamanlı operasyon", "Riskli sürüş olayları", "Kanıt yönetimi", "Koçluk", "Yol riski ve harita"]) {
    await expect(page.getByRole("heading", { name: capability })).toBeVisible();
  }
  // Nothing on the public page overclaims.
  await expect(page.getByText(/kazaları önler/i)).toHaveCount(0);
  expect(apiCalls).toEqual([]);
});

test("ana sayfa CTA'ları giriş ve kayıt ekranlarına götürür", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("main").getByRole("link", { name: "Giriş yap" }).click();
  await expect(page).toHaveURL(/\/giris$/);
  await expect(page.getByRole("heading", { name: "Giriş yapın" })).toBeVisible();

  await page.goto("/");
  await page.getByRole("main").getByRole("link", { name: "Yeni organizasyon oluştur" }).first().click();
  await expect(page).toHaveURL(/\/kayit$/);
  await expect(page.getByLabel("Organizasyon adı")).toBeVisible();
});

test("genel demo panel yalnızca sentetik veri gösterir ve hiçbir özel API'yi çağırmaz", async ({ page }) => {
  const apiCalls = trackApiCalls(page);
  await page.goto("/");
  await page.getByRole("main").getByRole("link", { name: /Demoyu keşfet/ }).first().click();
  await expect(page).toHaveURL(/\/demo$/);
  await expect(page.getByRole("heading", { name: "Demo panel · Genel Bakış" })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("yalnızca sentetik veri");
  await expect(page.getByText("Sentetik", { exact: true }).first()).toBeVisible();

  // KPIs, events, distributions and the driver ranking render from fixtures.
  await expect(page.getByText("Aktif araç", { exact: true })).toBeVisible();
  await expect(page.getByText("126", { exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "Sürücü risk sıralaması (sentetik)" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Sentetik araçlar, olaylar ve yol riski alanları" })).toBeVisible();

  const events = page.getByRole("list", { name: "Son güvenlik olayları (sentetik)" });
  await events.getByRole("button", { name: /Hız aşımı · 06 DMO 219/ }).click();
  const detail = page.getByRole("region", { name: "Seçili olay ayrıntısı" });
  await expect(detail.getByRole("heading", { name: "Hız aşımı · 06 DMO 219" })).toBeVisible();
  await expect(detail).toContainText("Ölçülen 146 km/sa, eşik 120 km/sa.");

  // Review actions never act; they explain and point to the real app.
  await detail.getByRole("button", { name: "Onayla" }).click();
  await expect(detail).toContainText("demo panelde çalışmaz");
  await detail.getByRole("link", { name: "Giriş yap" }).click();
  await expect(page).toHaveURL(/\/giris$/);

  expect(apiCalls).toEqual([]);
});

test("harita çalışanı derlemeyle birlikte sunulur", async ({ request }) => {
  // MapLibre's worker must be served as JavaScript or GeoJSON layers never draw.
  const response = await request.get("/maplibre/maplibre-gl-worker.mjs");
  expect(response.ok()).toBeTruthy();
  expect(response.headers()["content-type"]).toMatch(/javascript/);
  expect((await request.get("/maplibre/maplibre-gl-shared.mjs")).ok()).toBeTruthy();
});

test("oturum açmış kullanıcı ana sayfadan panele geçer; kimlik doğrulama değişmez", async ({ page }) => {
  const account = newAccount("genel");
  await register(page, account);

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Oturumunuz açık/ })).toBeVisible();
  await page.getByRole("banner").getByRole("link", { name: "Panele git" }).click();
  await expect(page).toHaveURL(/\/panel$/);
  await expect(page.getByRole("heading", { name: "Genel Bakış" })).toBeVisible();

  // Signed-in users visiting the login page still land on the dashboard.
  await page.goto("/giris");
  await expect(page).toHaveURL(/\/panel$/);

  // The public demo stays synthetic for signed-in users too.
  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: "Demo panel · Genel Bakış" })).toBeVisible();
});

test("oturum olmadan panel hâlâ giriş ekranına yönlendirir", async ({ page }) => {
  await page.goto("/panel");
  await expect(page).toHaveURL(/\/giris/);
});
