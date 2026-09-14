import { expect, test, type Page } from "@playwright/test";
import { API_URL } from "./support/env";
import {
  apiAccessToken,
  ingestHarshBraking,
  newAccount,
  register,
  verifyEmail,
  waitForFirstEvent,
} from "./support/flows";

const JPEG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(2048, 1)]);

test.describe.serial("filo güvenliği operasyonu", () => {
  const account = newAccount("operasyon");
  const vehicleId = "34E2E01";
  const sourceKey = "tele-e2e";
  let page: Page;
  let apiKey = "";
  let eventId = "";

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await register(page, account);
    await verifyEmail(page, account);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("araç, sürücü, veri kaynağı ve API anahtarı oluşturulur", async () => {
    await page.goto("/panel/araclar");
    await page.getByLabel("Dış kimlik").fill(vehicleId);
    await page.getByRole("button", { name: "Araç ekle" }).click();
    await expect(page.getByRole("cell", { name: vehicleId })).toBeVisible();

    await page.goto("/panel/surucular");
    await page.getByLabel("Dış kimlik").fill("SUR-E2E");
    await page.getByLabel("Ad soyad").fill("Kemal Sürücü");
    await page.getByRole("button", { name: "Sürücü ekle" }).click();
    await expect(page.getByRole("cell", { name: "Kemal Sürücü" })).toBeVisible();

    await page.goto("/panel/entegrasyonlar");
    await page.getByLabel("Ad", { exact: true }).fill("Telematik");
    await page.getByLabel("Kaynak anahtarı").fill(sourceKey);
    await page.getByRole("button", { name: "Oluştur" }).click();
    await expect(page.getByRole("cell", { name: sourceKey })).toBeVisible();
    await page.getByRole("button", { name: "Anahtar üret" }).click();
    apiKey = ((await page.getByLabel("Yeni API anahtarı").textContent()) ?? "").trim();
    expect(apiKey).toMatch(/^vrk_/);
  });

  test("telemetri güvenlik olayı üretir; olay koçluk atamasıyla incelenir", async ({ request }) => {
    const token = await apiAccessToken(request, account.email, account.password);
    await page.goto("/panel/surucular");
    await page.getByLabel("Kemal Sürücü için araç").selectOption({ label: vehicleId });
    await page.getByRole("button", { name: "Ata", exact: true }).click();
    await expect(page.getByText("Sürücü araca atandı.")).toBeVisible();

    await ingestHarshBraking(request, apiKey, sourceKey, vehicleId);
    eventId = await waitForFirstEvent(request, token);

    await page.goto("/panel/olaylar");
    await page.getByRole("link", { name: "İncele" }).first().click();
    await expect(page).toHaveURL(new RegExp(`/panel/olaylar/${eventId}`));
    await page.getByLabel("Çözüm").selectOption("kocluk_atandi");
    await page.getByLabel("Koçluk sorumlusu").selectOption({ index: 1 });
    await page.getByRole("button", { name: "İncelemeyi kaydet" }).click();
    await expect(page.locator('a[href^="/panel/kocluk/"]')).toBeVisible();
  });

  test("koçluk görevi başlatılır ve tamamlanır", async () => {
    await page.locator('a[href^="/panel/kocluk/"]').first().click();
    await page.getByRole("button", { name: "Başlat" }).click();
    await page.getByRole("button", { name: "Tamamlandı olarak işaretle" }).click();
    await expect(page.getByText("Görev tamamlandı.")).toBeVisible();
  });

  test("olaya kanıt görüntüsü eklenir ve anonimleştirme durumu dürüstçe gösterilir", async () => {
    await page.goto(`/panel/olaylar/${eventId}`);
    await page.getByLabel("Görüntü veya video kanıtı ekle").setInputFiles({
      name: "kabin.jpg",
      mimeType: "image/jpeg",
      buffer: JPEG,
    });
    await page.getByRole("button", { name: "Yükle" }).click();
    await expect(page.getByText("Kanıt dosyası doğrulandı ve olaya eklendi.")).toBeVisible();
    await expect(page.getByText("Anonimleştirilmedi (yüz/plaka görünebilir)")).toBeVisible();
    await expect(page.getByRole("button", { name: "Güvenli bağlantıyla aç" })).toBeVisible();
  });

  test("canlı operasyon sayfası anlık bağlantı kurar", async () => {
    await page.goto("/panel/canli");
    await expect(page.getByText("Anlık bağlantı açık")).toBeVisible({ timeout: 20_000 });
  });

  test("KVKK: sürücü verisi dışa aktarılır ve indirilebilir olur", async () => {
    await page.goto("/panel/gizlilik");
    await page.getByLabel("Kişi", { exact: true }).selectOption({ label: "Kemal Sürücü (SUR-E2E)" });
    await page.getByRole("button", { name: "Dışa aktarma talebi oluştur" }).click();
    await expect(page.getByText("Talep oluşturuldu; birkaç dakika içinde işlenecek.")).toBeVisible();
    await expect(page.getByRole("button", { name: "İndir" })).toBeVisible({ timeout: 45_000 });
  });

  test("raporlar indirilir ve bildirim kuralı oluşturulur", async () => {
    await page.goto("/panel/raporlar");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "İndir" }).first().click();
    expect((await download).suggestedFilename()).toMatch(/\.csv$/);

    await page.goto("/panel/bildirimler");
    await page.getByLabel("Kural adı").fill("Yüksek şiddet uyarısı");
    await page.getByRole("button", { name: "Kural ekle" }).click();
    await expect(page.getByText("Kural oluşturuldu.")).toBeVisible();
    await expect(page.getByText("Yüksek şiddet uyarısı")).toBeVisible();
  });

  test("saklama süresi kaydedilir ve abonelik kullanımı görüntülenir", async () => {
    await page.goto("/panel/gizlilik");
    await page.getByLabel("Ham telemetri (konum/hız noktaları)").fill("60");
    await page.getByRole("button", { name: "Kaydet" }).click();
    await expect(page.getByText("Saklama süreleri güncellendi.")).toBeVisible();

    await page.goto("/panel/abonelik");
    await expect(page.getByRole("heading", { name: "Abonelik" })).toBeVisible();
    await expect(page.getByText(/Deneme sürenizin bitmesine \d+ gün kaldı/)).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "Araç kullanımı" })).toHaveAttribute("aria-valuenow", "1");
  });

  test("API anahtarı panelden iptal edilir ve artık kabul edilmez", async ({ request }) => {
    await page.goto("/panel/entegrasyonlar");
    await page.getByRole("button", { name: "İptal et" }).first().click();
    await page.getByRole("button", { name: "Emin misiniz? Onayla" }).click();
    await expect(page.getByText("İptal edildi")).toBeVisible();
    const rejected = await request.post(`${API_URL}/api/v1/ingest/events`, {
      headers: { "X-API-Key": apiKey },
      data: { source_key: sourceKey, events: [] },
    });
    expect(rejected.status()).toBe(401);
  });
});
