import { test, expect } from "@playwright/test";

test("logging a rejection interaction surfaces discard sheet and discards app", async ({ page }) => {
  let appStatus: "draft" | "discarded" = "draft";
  let patchSeen: Record<string, unknown> | null = null;

  const buildApp = () => ({
    id: "a1",
    display_id: 1,
    url: "https://x.test/j",
    status: appStatus,
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
    folder_name: "a1-folder",
    notes: null,
    discard_note: null,
    discard_reason_id: null,
    discard_interaction_id: null,
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
      reference_number: null,
      mentions_home_office_policy: null,
      mentions_part_time: null,
    },
  });

  await page.route("**/api/auth/me", (r) =>
    r.fulfill({
      status: 200,
      body: JSON.stringify({ id: "u", email: "x@y.z", display_name: "X", oauth_enabled: false }),
    }),
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

  await page.route("**/api/applications*", async (route, req) => {
    const url = req.url();
    // Only handle bare /api/applications (list) here, not /a1 or /a1/...
    if (/\/api\/applications(\?|$)/.test(url)) {
      if (req.method() === "GET") {
        return route.fulfill({ status: 200, body: JSON.stringify([buildApp()]) });
      }
    }
    return route.fallback();
  });

  await page.route("**/api/applications/a1", async (route, req) => {
    if (req.method() === "GET") {
      return route.fulfill({ status: 200, body: JSON.stringify(buildApp()) });
    }
    if (req.method() === "PATCH") {
      patchSeen = JSON.parse(req.postData() || "{}");
      appStatus = "discarded";
      return route.fulfill({ status: 200, body: JSON.stringify(buildApp()) });
    }
    return route.fallback();
  });

  await page.route("**/api/applications/a1/timeline", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/applications/a1/chat", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/applications/a1/interviews", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );

  let interactionsList: Array<Record<string, unknown>> = [];
  await page.route("**/api/applications/a1/interactions", async (route, req) => {
    if (req.method() === "POST") {
      const created = {
        id: "i1",
        application_id: "a1",
        occurred_at: new Date().toISOString(),
        direction: "in",
        channel: "mail",
        subject: null,
        body: "Leider...",
        contact_name: null,
        contact_handle: null,
        sentiment: "rejection",
        created_from: "manual",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      interactionsList = [created];
      return route.fulfill({
        status: 200,
        body: JSON.stringify({
          interaction: created,
          suggest_discard: { reason_slug: "rejected", interaction_id: "i1" },
        }),
      });
    }
    return route.fulfill({ status: 200, body: JSON.stringify(interactionsList) });
  });

  await page.route("**/api/discard-reasons*", (r) =>
    r.fulfill({
      status: 200,
      body: JSON.stringify([
        { id: "dr-no-reply", slug: "no_reply", label: "No reply", is_system: true, is_archived: false, sort_order: 0, usage_count: 0 },
        { id: "dr-rejected", slug: "rejected", label: "Rejected", is_system: true, is_archived: false, sort_order: 1, usage_count: 0 },
      ]),
    }),
  );

  await page.goto("/applications/a1");
  // Wait for app detail to load.
  await expect(page.locator('a[href="https://x.test/j"]')).toBeVisible();

  // Open the Log interaction modal.
  await page.click("button:has-text('+ Log interaction')");
  await expect(page.locator("text=Log interaction")).toBeVisible();

  // Set direction = "in" (first select inside the modal).
  const modal = page.locator("div.fixed.inset-0");
  const selects = modal.locator("select");
  await selects.nth(0).selectOption("in");
  // Channel select (second select) — keep "mail" but set it explicitly.
  await selects.nth(1).selectOption("mail");
  // Fill body via placeholder.
  await page.getByPlaceholder("Body").fill("Leider...");
  // Sentiment select now appears (third select when direction === "in").
  await modal.locator("select").last().selectOption("rejection");

  // Save the interaction.
  await page.click("button:has-text('Save')");

  // The discard follow-up sheet should appear.
  await expect(page.locator("text=This was a rejection.")).toBeVisible();

  // Click "Discard app" to issue the PATCH.
  await page.click("button:has-text('Discard app')");

  // PATCH should have been called with status: discarded; status badge should refresh to "discarded".
  await expect.poll(() => patchSeen).not.toBeNull();
  expect((patchSeen as { status: string }).status).toBe("discarded");
  expect((patchSeen as { discard_interaction_id?: string }).discard_interaction_id).toBe("i1");

  // After PATCH, the refetched app shows status=discarded and the badge reflects it.
  await expect(page.locator("span.bg-orange-100:has-text('discarded')")).toBeVisible();
});
