import { test, expect } from "@playwright/test";

function row(over: Record<string, unknown>) {
  return {
    id: "x",
    display_id: 1,
    url: "https://x.test/j",
    status: "draft",
    job_state: "ready",
    job_error: null,
    failed_stage: null,
    language: "en",
    generated_md: null,
    has_docx: false,
    cv_variant_id: null,
    anschreiben_variant_id: null,
    job_posting_dirty: false,
    posting_online: null,
    labels: [],
    discard_reason_id: null,
    job_posting: {
      title: "Dev",
      company: "Acme",
      location: null,
      description: null,
      requirements: null,
      contact: null,
      deadline: null,
      salary: null,
      tech_stack: null,
      seniority: null,
      work_mode: null,
      benefits: null,
      language: "en",
      required_documents: null,
    },
    ...over,
  };
}

async function stubList(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/me", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify({ id: "u", email: "x@y.z", display_name: "X", oauth_enabled: false }) }),
  );
  await page.route("**/api/cv-variants", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/anschreiben-variants", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/labels", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/discard-reasons*", (r) => r.fulfill({ status: 200, body: "[]" }));

  const rows = [
    row({
      id: "a1",
      display_id: 1,
      job_posting: { ...row({}).job_posting, title: "Frontend Engineer", company: "Acme Corp", location: "Berlin" },
    }),
    row({
      id: "a2",
      display_id: 2,
      job_posting: { ...row({}).job_posting, title: "Backend Developer", company: "Globex", location: "Munich" },
    }),
  ];
  await page.route("**/api/applications*", async (route, req) => {
    if (req.method() === "GET") {
      return route.fulfill({ status: 200, body: JSON.stringify(rows) });
    }
    return route.fallback();
  });
}

test("search bar filters the list by title/company/location", async ({ page }) => {
  await stubList(page);
  await page.goto("/applications");

  // Both rows visible to start.
  await expect(page.locator("text=Frontend Engineer")).toBeVisible();
  await expect(page.locator("text=Backend Developer")).toBeVisible();

  const search = page.getByPlaceholder("Search title, company, location…");

  // Matches company of the second row only.
  await search.fill("globex");
  await expect(page.locator("text=Backend Developer")).toBeVisible();
  await expect(page.locator("text=Frontend Engineer")).toHaveCount(0);

  // Matches location of the first row only.
  await search.fill("berlin");
  await expect(page.locator("text=Frontend Engineer")).toBeVisible();
  await expect(page.locator("text=Backend Developer")).toHaveCount(0);

  // Clearing restores both.
  await search.fill("");
  await expect(page.locator("text=Frontend Engineer")).toBeVisible();
  await expect(page.locator("text=Backend Developer")).toBeVisible();
});

test("search with no matches shows an empty list", async ({ page }) => {
  await stubList(page);
  await page.goto("/applications");

  await page.getByPlaceholder("Search title, company, location…").fill("zzzznope");
  await expect(page.locator("text=Frontend Engineer")).toHaveCount(0);
  await expect(page.locator("text=Backend Developer")).toHaveCount(0);
});
