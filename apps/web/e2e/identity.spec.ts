import { expect, test } from "@playwright/test";
import { NEW_PASSWORD } from "./support/env";
import { login, logout, newAccount, register, verifyEmail } from "./support/flows";
import { oneTimeLink, waitForEmail } from "./support/mail";

test("kayıt, e-posta doğrulama, oturum yenileme, çıkış ve tekrar giriş", async ({ page }) => {
  const account = newAccount("kimlik");
  await register(page, account);
  await verifyEmail(page, account);

  await page.goto("/panel/hesap");
  await expect(page.getByText("E-posta doğrulandı", { exact: true })).toBeVisible();
  // The access token lives in memory only; a reload restores the session from
  // the HttpOnly refresh cookie.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Hesabım" })).toBeVisible();

  await logout(page);
  await login(page, account.email, account.password);
  await expect(page).toHaveURL(/\/panel$/);
});

test("hatalı parola Türkçe hata gösterir ve oturum açmaz", async ({ page }) => {
  const account = newAccount("hatali");
  await register(page, account);
  await logout(page);
  await login(page, account.email, "YanlisParola123!");
  await expect(page.getByRole("alert").filter({ hasText: "E-posta veya parola hatalı." })).toBeVisible();
  await expect(page).toHaveURL(/\/giris/);
});

test("parola sıfırlama e-posta bağlantısıyla tamamlanır", async ({ page }) => {
  const account = newAccount("sifre");
  await register(page, account);
  await logout(page);

  await page.goto("/sifremi-unuttum");
  await page.getByLabel("E-posta").fill(account.email);
  await page.getByRole("button", { name: "Sıfırlama bağlantısı gönder" }).click();
  await expect(page.getByRole("status")).toBeVisible();

  const email = await waitForEmail(account.email, "/sifre-sifirla");
  await page.goto(oneTimeLink(email, "/sifre-sifirla"));
  await page.getByLabel("Yeni parola", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Yeni parola (tekrar)").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Parolayı güncelle" }).click();
  await expect(page).toHaveURL(/\/giris\?sifre=guncellendi/);

  await login(page, account.email, account.password);
  await expect(page.getByRole("alert").filter({ hasText: "E-posta veya parola hatalı." })).toBeVisible();
  await login(page, account.email, NEW_PASSWORD);
  await expect(page).toHaveURL(/\/panel$/);
});

test("oturum olmadan panel sayfası giriş ekranına yönlendirir", async ({ page }) => {
  await page.goto("/panel/olaylar");
  await expect(page).toHaveURL(/\/giris/);
});
