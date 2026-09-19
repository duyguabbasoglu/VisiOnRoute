import { expect, test, type Route } from "@playwright/test";
import { API_URL } from "./support/env";
import { apiAccessToken, bearer, newAccount, register, verifyEmail } from "./support/flows";

const SEED_RESPONSE = {
  created: true,
  data_origin: "synthetic",
  environment: "demo",
  summary: { vehicles: 3, drivers: 4, trips: 9, telemetry_points: 540, safety_events: 11, road_risks: 2 },
  message: "Sentetik demo verisi oluşturuldu. Tüm kayıtlar sentetiktir ve gerçek kanıt değildir.",
};

test("boş organizasyon yönlendirmeli boş durum kartını görür; demo dışı ortamda sentetik veri reddedilir", async ({
  page,
  request,
}) => {
  const account = newAccount("bospanel");
  await register(page, account);
  await verifyEmail(page, account);

  await page.goto("/panel");
  await expect(page.getByRole("heading", { name: "Paneliniz henüz boş" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Araçlarınızı ekleyin" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Bir veri kaynağı ve API anahtarı tanımlayın" })).toBeVisible();
  // The E2E stack runs as a local environment: the seed option does not exist.
  await expect(page.getByRole("button", { name: "Sentetik demo verisi oluştur" })).toHaveCount(0);

  const token = await apiAccessToken(request, account.email, account.password);
  const denied = await request.post(`${API_URL}/api/v1/demo-data/seed`, bearer(token));
  expect(denied.status()).toBe(403);
  expect((await denied.json()).error.code).toBe("DEMO_DATA_UNAVAILABLE");
});

test("sentetik demo verisi oluşturma: yükleme durumu, tek istek ve sentetik veri bildirimi", async ({ page }) => {
  const account = newAccount("demotohum");
  await register(page, account);
  await verifyEmail(page, account);

  // Only the two demo-data endpoints are stubbed to simulate the demo
  // environment; the backend pipeline itself is covered by
  // tests/integration/test_demo_seed.py and the live deployment check.
  let seeded = false;
  let seedRequests = 0;
  let releaseSeed: () => void = () => undefined;
  const seedGate = new Promise<void>((resolve) => {
    releaseSeed = resolve;
  });
  await page.route("**/api/v1/demo-data", (route: Route) =>
    route.fulfill({
      json: seeded
        ? { available: false, seeded: true, reason: null, message: null }
        : { available: true, seeded: false, reason: null, message: null },
    }),
  );
  await page.route("**/api/v1/demo-data/seed", async (route: Route) => {
    seedRequests += 1;
    await seedGate;
    seeded = true;
    await route.fulfill({ json: SEED_RESPONSE });
  });

  await page.goto("/panel");
  const button = page.getByRole("button", { name: "Sentetik demo verisi oluştur" });
  await expect(button).toBeEnabled();
  await button.dblclick();

  const busy = page.getByRole("button", { name: "Sentetik veri oluşturuluyor…" });
  await expect(busy).toBeDisabled();
  await expect(page.getByText("Bu işlem birkaç saniye sürebilir.")).toBeVisible();
  await busy.click({ force: true });
  releaseSeed();

  await expect(page.getByText("Bu paneldeki veriler sentetiktir.")).toBeVisible();
  await expect(page.getByText(/3 araç, 4 sürücü, 9 sefer, 540 telemetri noktası/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Paneliniz henüz boş" })).toHaveCount(0);
  expect(seedRequests).toBe(1);
});
