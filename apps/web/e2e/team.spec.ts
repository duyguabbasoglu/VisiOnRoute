import { expect, test } from "@playwright/test";
import { PASSWORD } from "./support/env";
import { login, logout, newAccount, register, verifyEmail } from "./support/flows";
import { oneTimeLink, waitForEmail } from "./support/mail";
import { freshTotp, timeStep, totp } from "./support/totp";

test("davet edilen analist katılır ve yönetici bölümlerini göremez", async ({ page, browser }) => {
  const owner = newAccount("ekip");
  await register(page, owner);
  await verifyEmail(page, owner);

  const inviteeEmail = `analist-${owner.slug}@ornek.example`;
  await page.goto("/panel/ayarlar");
  await page.getByLabel("E-posta").fill(inviteeEmail);
  await page.locator("#invite-role").selectOption("analyst");
  await page.getByRole("button", { name: "Davet gönder" }).click();
  await expect(page.getByText(inviteeEmail).first()).toBeVisible();

  const invitation = await waitForEmail(inviteeEmail, "/davet");
  const context = await browser.newContext();
  const invitee = await context.newPage();
  await invitee.goto(oneTimeLink(invitation, "/davet"));
  await invitee.getByLabel("Ad soyad").fill("Ece Analist");
  await invitee.getByLabel("Parola", { exact: true }).fill(PASSWORD);
  await invitee.getByLabel("Parola (tekrar)").fill(PASSWORD);
  await invitee.getByRole("button", { name: "Daveti kabul et" }).click();
  await expect(invitee).toHaveURL(/\/giris/);

  await login(invitee, inviteeEmail, PASSWORD);
  await expect(invitee).toHaveURL(/\/panel$/);
  await expect(invitee.getByRole("link", { name: "Güvenlik Olayları" })).toBeVisible();
  await expect(invitee.getByRole("link", { name: "Gizlilik (KVKK)" })).toHaveCount(0);
  await invitee.goto("/panel/gizlilik");
  await expect(invitee.getByText("Bu sayfa yalnızca organizasyon sahipleri ve yöneticileri içindir.")).toBeVisible();
  await context.close();
});

test("iki adımlı doğrulama etkinleştirilir ve girişte kod istenir", async ({ page }) => {
  test.setTimeout(150_000);
  const account = newAccount("mfa");
  await register(page, account);

  await page.goto("/panel/hesap");
  await page.getByRole("button", { name: "İki adımlı doğrulamayı etkinleştir" }).click();
  await page.getByLabel("Güvenlik için parolanızı girin").fill(account.password);
  await page.getByRole("button", { name: "Devam" }).click();
  const secret = ((await page.locator("code").first().textContent()) ?? "").trim();
  expect(secret).toMatch(/^[A-Z2-7]+=*$/);

  const enrolledStep = timeStep();
  await page.getByLabel("Doğrulama kodu").fill(totp(secret, enrolledStep));
  await page.getByRole("button", { name: "Etkinleştir" }).click();
  await expect(page.getByRole("list", { name: "Kurtarma kodları" })).toBeVisible();

  await logout(page);
  await login(page, account.email, account.password);
  await expect(page.getByLabel("Doğrulama kodu")).toBeVisible();
  // Codes from an already used time step are rejected as replays.
  const { code } = await freshTotp(secret, enrolledStep);
  await page.getByLabel("Doğrulama kodu").fill(code);
  await page.getByRole("button", { name: "Doğrula ve giriş yap" }).click();
  await expect(page).toHaveURL(/\/panel$/);
});
