import { test, expect } from "@playwright/test";

test("happy path: add URL, poll until ready, see download", async ({ page }) => {
  let getCalls = 0;
  await page.route("**/api/auth/me", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify({ id: "u", email: "x@y.z", display_name: "X" }) }),
  );
  await page.route("**/api/cv-variants", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/anschreiben-variants", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/applications", async (route, req) => {
    if (req.method() === "POST") {
      return route.fulfill({
        status: 202,
        body: JSON.stringify({
          id: "a1", url: "https://x.test/j", status: "draft",
          job_state: "pending", job_error: null, language: null,
          generated_md: null, has_docx: false, job_posting: null,
          failed_stage: null, cv_variant_id: null,
          anschreiben_variant_id: null, job_posting_dirty: false,
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
        failed_stage: null, cv_variant_id: null,
        anschreiben_variant_id: null, job_posting_dirty: false,
        job_posting:
          s === "ready"
            ? {
                title: "Dev", company: "Acme", location: null,
                description: "d", requirements: "r", contact: null,
                deadline: null, salary: null,
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

test("URL-only add → state extracted → fields editable", async ({ page }) => {
  await page.route("**/api/auth/me", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify({ id: "u", email: "x@y.z", display_name: "X" }) }),
  );
  await page.route("**/api/cv-variants", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/anschreiben-variants", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );

  const extracted = {
    id: "app-1",
    url: "https://x.test/j",
    status: "draft",
    job_state: "extracted",
    job_error: null,
    failed_stage: null,
    language: "en",
    generated_md: null,
    has_docx: false,
    cv_variant_id: null,
    anschreiben_variant_id: null,
    job_posting_dirty: false,
    job_posting: {
      title: "Dev", company: "Acme", language: "en",
      location: null, description: null, requirements: null,
      contact: null, deadline: null,
      salary: null, tech_stack: null, seniority: null, work_mode: null,
      benefits: null,
    },
  };

  await page.route("**/api/applications", async (route, req) => {
    if (req.method() === "POST") {
      return route.fulfill({ status: 202, body: JSON.stringify(extracted) });
    }
    return route.fulfill({ status: 200, body: JSON.stringify([]) });
  });
  await page.route("**/api/applications/app-1", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify(extracted) }),
  );
  await page.route("**/api/applications/app-1/chat", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/applications/app-1/interviews", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );

  await page.goto("/applications");
  await page.fill("input[type=url]", "https://x.test/j");
  await page.click("button:has-text('Add')");
  await page.goto("/applications/app-1");
  await expect(page.locator("text=Extracted")).toBeVisible({ timeout: 10000 });
  // Title field renders the extracted value as an editable input
  const titleInput = page.locator("label:has-text('Title') + input");
  await expect(titleInput).toHaveValue("Dev");
});

test("delete from list removes the application after confirm", async ({ page }) => {
  let deleted = false;

  await page.route("**/api/auth/me", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify({ id: "u", email: "x@y.z", display_name: "X", oauth_enabled: false }) }),
  );
  await page.route("**/api/cv-variants", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/anschreiben-variants", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/labels", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );

  const baseRow = {
    id: "a1",
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
    job_posting: {
      title: "Dev",
      company: "Acme Corp",
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
  };

  await page.route("**/api/applications*", async (route, req) => {
    if (req.method() === "GET") {
      return route.fulfill({
        status: 200,
        body: JSON.stringify(deleted ? [] : [baseRow]),
      });
    }
    return route.fallback();
  });
  await page.route("**/api/applications/a1", async (route, req) => {
    if (req.method() === "DELETE") {
      deleted = true;
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fallback();
  });

  await page.goto("/applications");
  await expect(page.locator("text=Acme Corp")).toBeVisible();
  await page.locator('[aria-label="delete"]').first().click();
  await page.locator("button:has-text('Delete')").click();
  await expect(page.locator("text=Acme Corp")).toHaveCount(0);
});

test("contact block renders mailto and tel links when present", async ({ page }) => {
  await page.route("**/api/auth/me", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify({ id: "u", email: "x@y.z", display_name: "X", oauth_enabled: false }) }),
  );
  await page.route("**/api/cv-variants", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/anschreiben-variants", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/labels", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );

  const row = {
    id: "a2",
    display_id: 2,
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
    job_posting: {
      title: "Dev",
      company: "Acme",
      location: null,
      description: null,
      requirements: null,
      contact: {
        name: "Jane Doe",
        role: "Recruiter",
        email: "jane@acme.test",
        phone: "+49 30 1234567",
      },
      deadline: null,
      salary: null,
      tech_stack: null,
      seniority: null,
      work_mode: null,
      benefits: null,
      language: "en",
      required_documents: null,
    },
  };

  await page.route("**/api/applications/a2", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify(row) }),
  );
  await page.route("**/api/applications/a2/chat", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/applications/a2/interviews", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );

  await page.goto("/applications/a2");
  await expect(page.locator('a[href="mailto:jane@acme.test"]')).toBeVisible();
  await expect(page.locator('a[href="tel:+49 30 1234567"]')).toBeVisible();
  await expect(page.locator("text=Jane Doe")).toBeVisible();
});
