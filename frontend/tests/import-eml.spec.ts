import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const emlPath = path.join(here, "fixtures", "sample.eml");

test("import .eml creates interactions, shows toast, undo removes them", async ({ page }) => {
  const buildApp = () => ({
    id: "a1", display_id: 1, url: "https://x.test/j", status: "draft",
    job_state: "ready", job_error: null, failed_stage: null, language: "en",
    generated_md: null, has_docx: false, cv_variant_id: null,
    anschreiben_variant_id: null, job_posting_dirty: false, posting_online: null,
    labels: [], folder_name: "a1-folder", notes: null, discard_note: null,
    discard_reason_id: null, discard_interaction_id: null,
    job_posting: {
      title: "Dev", company: "Acme", location: null, description: null,
      requirements: null, contact: null, deadline: null, salary: null,
      tech_stack: null, seniority: null, work_mode: null, benefits: null,
      language: "en", required_documents: null, reference_number: null,
      mentions_home_office_policy: null, mentions_part_time: null,
    },
  });

  await page.route("**/api/auth/me", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify({ id: "u", email: "me@self.test", display_name: "X", oauth_enabled: false }) }));
  await page.route("**/api/cv-variants", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/anschreiben-variants", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/labels", (r) => r.fulfill({ status: 200, body: "[]" }));
  await page.route("**/api/applications/a1", (r) => r.fulfill({ status: 200, body: JSON.stringify(buildApp()) }));
  await page.route("**/api/applications/a1/chat", (r) => r.fulfill({ status: 200, body: "[]" }));

  const created = {
    id: "i1", application_id: "a1", occurred_at: new Date().toISOString(),
    direction: "in", channel: "mail", subject: "Re: Your application",
    body: "Thanks, we received your CV.", contact_name: "Recruiter Anna",
    contact_handle: "anna@acme.test", sentiment: null, created_from: "eml_import",
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  };

  let timelineRows: Array<Record<string, unknown>> = [];
  await page.route("**/api/applications/a1/timeline", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify(timelineRows) }));

  await page.route("**/api/applications/a1/interactions/import-eml", (r) => {
    timelineRows = [{ kind: "interaction", at: created.occurred_at, data: created }];
    return r.fulfill({ status: 200, body: JSON.stringify({ interactions: [created], count: 1, used_llm: false }) });
  });

  await page.route("**/api/interactions/i1", (r) => {
    timelineRows = [];
    return r.fulfill({ status: 204, body: "" });
  });

  await page.goto("/applications/a1");
  await expect(page.locator('a[href="https://x.test/j"]')).toBeVisible();

  // Set the hidden .eml file input (drag-drop of OS files is unreliable in Playwright).
  await page.setInputFiles('input[type="file"][accept=".eml"]', emlPath);

  // Timeline (default tab) re-renders with the imported row.
  await expect(page.locator("text=Re: Your application")).toBeVisible();

  // Toast with Undo appears.
  await expect(page.locator("text=Imported 1 interaction")).toBeVisible();
  await page.click("button:has-text('Undo')");

  // After undo, the row is gone.
  await expect(page.locator("text=Re: Your application")).toHaveCount(0);
});
