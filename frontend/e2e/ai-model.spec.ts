import { expect, test } from "@playwright/test";

// Founder F2 and F3 (M7a gate) in a real Chromium: the key box is masked without being a password field, so the
// browser's password manager has nothing to offer to save, and the provider follows the key's shape.
test("the API key box is masked, is no password field, and finds the provider", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  const key = page.getByTestId("ai-key");
  await expect(key).toBeVisible();
  await key.fill("AIzaSyFAKE-not-a-real-key-000000");
  expect(await key.getAttribute("type")).toBe("text");
  expect(await key.evaluate((el) => getComputedStyle(el).getPropertyValue("-webkit-text-security"))).toBe("disc");
  expect(await key.evaluate((el) => el.closest("form"))).toBeNull();
  await expect(page.locator('[data-testid="ai-model-card"] input[type="password"]')).toHaveCount(0);
  await expect(page.getByLabel("Model provider")).toHaveValue("gemini");
  await expect(page.getByTestId("ai-key-hint")).toContainText("Looks like a Gemini key");
  await expect(page.getByLabel("Server address")).toHaveCount(0); // Advanced is for Custom only
  await page.getByTestId("ai-model-card").screenshot({ path: "test-results/ai-model-card.png" });
});
