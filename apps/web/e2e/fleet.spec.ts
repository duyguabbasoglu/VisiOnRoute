import { expect, test, type Page } from "@playwright/test";
import { API_URL, PASSWORD } from "./support/env";
import { apiAccessToken, bearer, login, newAccount, register, seedEventViaApi, verifyEmail } from "./support/flows";
import { oneTimeLink, waitForEmail } from "./support/mail";

const NAV_SECTIONS: [link: string, heading: string][] = [
  ["Genel Bakış", "Genel Bakış"],
  ["Canlı Operasyon", "Canlı Operasyon"],
  ["Harita", "Harita"],
  ["Seferler", "Seferler"],
  ["Güvenlik Olayları", "Güvenlik Olayları"],
  ["Koçluk", "Koçluk"],
  ["Yol Riskleri", "Yol Riskleri"],
  ["Analizler", "Analizler"],
  ["Raporlar", "Raporlar"],
  ["Filolar", "Filolar"],
  ["Araçlar", "Araçlar"],
  ["Sürücüler", "Sürücüler"],
  ["Cihazlar ve Kameralar", "Cihazlar ve Kameralar"],
  ["Bildirimler", "Bildirimler"],
  ["Entegrasyonlar", "Entegrasyonlar"],
  ["Organizasyon", "Organizasyon"],
  ["Gizlilik (KVKK)", "Gizlilik (KVKK)"],
  ["Abonelik", "Abonelik"],
  ["Hesabım", "Hesabım"],
];

test.describe.serial("filo yapısı, cihazlar, harita ve yetki sınırları", () => {
  const account = newAccount("filo");
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    // Maps must not depend on third-party tile servers during tests.
    await page.route("https://tile.openstreetmap.org/**", (route) => route.abort());
    await register(page, account);
    await verifyEmail(page, account);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("filo oluşturulur, araç filoya eklenir ve düzenlenir", async () => {
    await page.goto("/panel/filolar");
    await page.getByLabel("Filo adı").fill("Marmara Dağıtım");
    await page.getByLabel("Bölge").fill("İstanbul");
    await page.getByRole("button", { name: "Filo oluştur" }).click();
    await expect(page.getByText("“Marmara Dağıtım” filosu oluşturuldu.")).toBeVisible();

    await page.goto("/panel/araclar");
    await page.getByLabel("Dış kimlik").fill("34FLT01");
    await page.getByLabel("Plaka", { exact: true }).fill("34 FLT 01");
    await page.getByLabel("Model yılı").fill("1900");
    await expect(page.getByText("1950–2100 arasında bir yıl girin.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Araç ekle" })).toBeDisabled();
    await page.getByLabel("Model yılı").fill("2021");
    await page.getByLabel("Filo", { exact: true }).selectOption({ label: "Marmara Dağıtım" });
    await page.getByRole("button", { name: "Araç ekle" }).click();
    await expect(page.getByText("34 FLT 01 eklendi.")).toBeVisible();

    await page.getByRole("button", { name: "34FLT01 aracını düzenle" }).click();
    const editor = page.getByRole("form", { name: "34FLT01 aracını düzenle" });
    await editor.getByLabel("Durum").selectOption("maintenance");
    await editor.getByRole("button", { name: "Kaydet" }).click();
    await expect(page.getByText("Araç güncellendi.")).toBeVisible();
    await expect(page.getByRole("row", { name: /34FLT01.*Marmara Dağıtım.*Bakımda/ })).toBeVisible();

    await page.goto("/panel/filolar");
    await expect(page.getByRole("row", { name: /Marmara Dağıtım.*İstanbul.*1/ })).toBeVisible();
  });

  test("cihaz ve kamera kaydedilir; cihaz pasifleştirilir", async () => {
    await page.goto("/panel/cihazlar");
    await page.getByLabel("Cihaz dış kimliği").fill("TLM-E2E-1");
    await page.getByLabel("Cihaz türü").selectOption("dashcam");
    await page.getByLabel("Takılı olduğu araç").selectOption({ label: "34 FLT 01" });
    await page.getByRole("button", { name: "Cihaz ekle" }).click();
    await expect(page.getByText("TLM-E2E-1 cihazı kaydedildi.")).toBeVisible();

    const deviceRow = page.getByRole("table", { name: "Cihazlar" }).getByRole("row", { name: /TLM-E2E-1/ });
    await expect(deviceRow.getByText("Etkin", { exact: true })).toBeVisible();
    await deviceRow.getByRole("button", { name: "Pasifleştir" }).click();
    await deviceRow.getByRole("button", { name: "Pasifleştir" }).click();
    await expect(deviceRow.getByText("Pasif", { exact: true })).toBeVisible();

    await page.getByLabel("Kamera dış kimliği").fill("CAM-E2E-1");
    await page.getByLabel("Konum", { exact: true }).selectOption("driver");
    await page.getByLabel("Bağlı cihaz").selectOption({ label: "TLM-E2E-1" });
    await page.getByRole("button", { name: "Kamera ekle" }).click();
    await expect(page.getByText("CAM-E2E-1 kamerası kaydedildi.")).toBeVisible();
    await expect(page.getByRole("table", { name: "Kameralar" }).getByRole("row", { name: /CAM-E2E-1.*Sürücü.*TLM-E2E-1/ })).toBeVisible();
  });

  test("telemetri seferi haritada ve sefer ayrıntısında görünür", async ({ request }) => {
    const token = await apiAccessToken(request, account.email, account.password);
    const eventId = await seedEventViaApi(request, token);

    await page.goto("/panel/harita");
    const mapRegion = page.getByRole("region", { name: "Filo haritası" });
    await expect(mapRegion).toBeVisible();
    // Regression: MapLibre restyles its container, which once collapsed it to 0 px.
    expect((await mapRegion.boundingBox())?.height ?? 0).toBeGreaterThan(200);
    // The canvas itself only exists where the browser provides WebGL.
    const hasWebgl = await page.evaluate(() => {
      const probe = document.createElement("canvas");
      return Boolean(probe.getContext("webgl2") ?? probe.getContext("webgl"));
    });
    if (hasWebgl) await expect(page.locator(".maplibregl-canvas").first()).toBeVisible();
    await expect(page.getByRole("link", { name: "İncele" }).first()).toHaveAttribute("href", `/panel/olaylar/${eventId}`);

    await page.goto("/panel/seferler");
    await page.getByRole("link", { name: "Ayrıntı" }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: /^Sefer · / })).toBeVisible();
    await expect(page.getByRole("region", { name: "Sefer güzergâhı" })).toBeVisible();
    await expect(page.getByRole("link", { name: "İncele" })).toHaveAttribute("href", `/panel/olaylar/${eventId}`);

    await page.goto(`/panel/olaylar/${eventId}`);
    await expect(page.getByRole("region", { name: "Olay konumu" })).toBeVisible();
  });

  test("tüm ana bölümlere menüden ulaşılır", async () => {
    await page.goto("/panel");
    const menu = page.getByRole("navigation", { name: "Ana menü" });
    for (const [link, heading] of NAV_SECTIONS) {
      await menu.getByRole("link", { name: link, exact: true }).click();
      await expect(page.getByRole("heading", { level: 1, name: heading, exact: true })).toBeVisible();
    }
    await page.goto("/panel/bu-sayfa-yok");
    await expect(page.getByRole("heading", { name: "Sayfa bulunamadı" })).toBeVisible();
  });

  test("salt okunur analist filo kaydı değiştiremez (arayüz ve API)", async ({ browser, request }) => {
    const analystEmail = `analist-${account.slug}@ornek.example`;
    await page.goto("/panel/ayarlar");
    await page.getByLabel("E-posta").fill(analystEmail);
    await page.locator("#invite-role").selectOption("analyst");
    await page.getByRole("button", { name: "Davet gönder" }).click();
    await expect(page.getByText(analystEmail).first()).toBeVisible();

    const invitation = await waitForEmail(analystEmail, "/davet");
    const context = await browser.newContext();
    const analyst = await context.newPage();
    await analyst.route("https://tile.openstreetmap.org/**", (route) => route.abort());
    await analyst.goto(oneTimeLink(invitation, "/davet"));
    await analyst.getByLabel("Ad soyad").fill("Ece Analist");
    await analyst.getByLabel("Parola", { exact: true }).fill(PASSWORD);
    await analyst.getByLabel("Parola (tekrar)").fill(PASSWORD);
    await analyst.getByRole("button", { name: "Daveti kabul et" }).click();
    await expect(analyst).toHaveURL(/\/giris/);
    await login(analyst, analystEmail, PASSWORD);
    await expect(analyst).toHaveURL(/\/panel$/);

    await analyst.goto("/panel/filolar");
    await expect(analyst.getByRole("cell", { name: "Marmara Dağıtım" })).toBeVisible();
    await expect(analyst.getByRole("button", { name: "Filo oluştur" })).toHaveCount(0);

    await analyst.goto("/panel/cihazlar");
    await expect(analyst.getByRole("table", { name: "Cihazlar" }).getByRole("row", { name: /TLM-E2E-1/ })).toBeVisible();
    await expect(analyst.getByRole("button", { name: "Cihaz ekle" })).toHaveCount(0);
    await expect(analyst.getByRole("button", { name: /Pasifleştir|Etkinleştir/ })).toHaveCount(0);

    await analyst.goto("/panel/yol-riskleri");
    await expect(analyst.getByRole("heading", { level: 1, name: "Yol Riskleri" })).toBeVisible();
    await expect(analyst.getByRole("button", { name: "Alan oluştur" })).toHaveCount(0);
    await context.close();

    const ownerToken = await apiAccessToken(request, account.email, account.password);
    const devices = (await (await request.get(`${API_URL}/api/v1/devices`, bearer(ownerToken))).json()) as {
      items: { id: string }[];
    };
    const analystToken = await apiAccessToken(request, analystEmail, PASSWORD);
    const denied = await request.patch(`${API_URL}/api/v1/devices/${devices.items[0]?.id}`, {
      ...bearer(analystToken),
      data: { status: "active" },
    });
    expect(denied.status()).toBe(403);
  });
});
