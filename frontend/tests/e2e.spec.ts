import { test, expect } from "@playwright/test";

test("happy path: add URL, poll until ready, see download", async ({ page }) => {
  let getCalls = 0;
  await page.route("**/api/auth/me", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify({ id: "u", email: "x@y.z", display_name: "X" }) }),
  );
  await page.route("**/api/applications", async (route, req) => {
    if (req.method() === "POST") {
      return route.fulfill({
        status: 202,
        body: JSON.stringify({
          id: "a1", url: "https://x.test/j", status: "draft",
          job_state: "pending", job_error: null, language: null,
          generated_md: null, has_docx: false, job_posting: null,
        }),
      });
    }
    return route.fulfill({ status: 200, body: JSON.stringify([]) });
  });
  await page.route("**/api/applications/a1", (route) => {
    getCalls++;
    const states = ["pending", "extracting", "ready"];
    const s = states[Math.min(getCalls - 1, states.length - 1)];
    return route.fulfill({
      status: 200,
      body: JSON.stringify({
        id: "a1", url: "https://x.test/j", status: "draft",
        job_state: s, job_error: null, language: "en",
        generated_md: s === "ready" ? "# Hello" : null,
        has_docx: s === "ready",
        job_posting:
          s === "ready"
            ? {
                title: "Dev", company: "Acme", location: null,
                description: "d", requirements: "r", contact_person: null,
                application_email: null, deadline: null, salary: null,
                tech_stack: ["python"], seniority: null, work_mode: null,
                benefits: null, language: "en",
              }
            : null,
      }),
    });
  });
  await page.route("**/api/applications/a1/chat", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/applications/a1/interviews", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );

  await page.goto("/applications");
  await page.fill("input[type=url]", "https://x.test/j");
  await page.click("button:has-text('Add')");
  await page.goto("/applications/a1");
  await expect(page.locator("text=Dev")).toBeVisible({ timeout: 10000 });
  await expect(page.locator("a:has-text('Download DOCX')")).toBeVisible();
});
