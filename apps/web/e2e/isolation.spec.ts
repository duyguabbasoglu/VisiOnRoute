import { expect, test } from "@playwright/test";
import { API_URL } from "./support/env";
import { apiAccessToken, bearer, newAccount, register, seedEventViaApi, verifyEmail } from "./support/flows";

test("bir organizasyon başka organizasyonun olayını göremez (arayüz ve API)", async ({ browser, request }) => {
  const tenantA = newAccount("kiraci-a");
  const pageA = await browser.newPage();
  await register(pageA, tenantA);
  await verifyEmail(pageA, tenantA);
  const tokenA = await apiAccessToken(request, tenantA.email, tenantA.password);
  const eventId = await seedEventViaApi(request, tokenA);
  await pageA.goto(`/panel/olaylar/${eventId}`);
  await expect(pageA.getByRole("heading", { name: "Açıklama" })).toBeVisible();
  await pageA.close();

  const tenantB = newAccount("kiraci-b");
  const context = await browser.newContext();
  const pageB = await context.newPage();
  await register(pageB, tenantB);
  await pageB.goto(`/panel/olaylar/${eventId}`);
  await expect(pageB.getByText(/bulunamadı/i).first()).toBeVisible();
  await expect(pageB.getByRole("heading", { name: "Açıklama" })).toHaveCount(0);

  const tokenB = await apiAccessToken(request, tenantB.email, tenantB.password);
  const response = await request.get(`${API_URL}/api/v1/safety-events/${eventId}`, bearer(tokenB));
  expect(response.status()).toBe(404);
  await context.close();
});
