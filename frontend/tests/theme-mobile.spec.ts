import { test, expect } from "@playwright/test";

async function stubAuth(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/me", (r) =>
    r.fulfill({
      status: 200,
      body: JSON.stringify({ id: "u", email: "x@y.z", display_name: "X", oauth_enabled: false }),
    }),
  );
  await page.route("**/api/cv-variants", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/anschreiben-variants", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/labels", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/applications*", (r) => r.fulfill({ status: 200, body: "[]" }));
}

test("theme toggle flips .dark and persists across reload", async ({ page }) => {
  await stubAuth(page);
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/applications");

  const html = page.locator("html");
  await expect(html).not.toHaveClass(/dark/);

  await page.getByRole("button", { name: /dark theme/i }).click();
  await expect(html).toHaveClass(/dark/);

  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
});

test("mobile shows drawer toggle; desktop hides it", async ({ page }) => {
  await stubAuth(page);

  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/applications");
  const menuBtn = page.getByRole("button", { name: "Open menu" });
  await expect(menuBtn).toBeVisible();

  await menuBtn.click();
  const drawer = page.locator("#mobile-drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("link", { name: "Stats" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);

  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page.getByRole("button", { name: "Open menu" })).toHaveCount(0);
});
