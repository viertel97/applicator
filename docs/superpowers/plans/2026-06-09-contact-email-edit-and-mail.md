# Contact Email Edit + Mail-from-Log-Interaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user add/edit a job posting's contact email anywhere it's missing, and have an email typed while logging a mail interaction drive "Open in mail" live and persist back onto the posting.

**Architecture:** Frontend-only persistence reusing the existing `PATCH /{aid}/job-posting` (its `JobPostingPatch` already accepts `contact`). One backend guard stops contact-only patches from setting `job_posting_dirty`. Three React components are wired: `ContactBlock` becomes editable, `JobPostingPanel` manages nested contact draft state, `InteractionLogModal` prefers the typed recipient and writes it back on save.

**Tech Stack:** FastAPI + SQLAlchemy + pytest/testcontainers (backend); React 18 + TypeScript + TanStack Query, `tsc` typecheck (frontend).

**Spec:** `docs/superpowers/specs/2026-06-08-contact-email-edit-and-mail-design.md`

**Environment notes:**
- Backend tests use testcontainers Postgres — run with the sandbox OFF (needs Docker).
- Frontend has no component test runner; verification is `tsc` typecheck + manual against the built Docker image. Run `tsc` via the raw node binary with sandbox OFF (the rtk proxy summarizes away real `tsc` errors).
- Docker image build is blocked in this harness (keychain cred error -50). The human rebuilds the image and brings local images up with `--no-deps` for the manual-verification task.

---

### Task 1: Backend — contact-only patch must not mark posting dirty

**Files:**
- Modify: `backend/app/api/applications.py:368-372` (`patch_job_posting`)
- Test: `backend/tests/integration/test_jobposting_patch.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/integration/test_jobposting_patch.py` (mirrors `test_patch_job_posting_sets_dirty_after_generate`, but patches only `contact`):

```python
def test_patch_contact_only_keeps_dirty_false_after_generate(
    monkeypatch, auth_user, db_session, tmp_path
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/c", status_code=200, html="<p>x</p>", text="x" * 1000)
    payload = {"title": "Dev", "company": "Acme", "language": "en"}
    _eager_patch(monkeypatch, db_session, settings,
                 lambda m, s: json.dumps(payload) if s else "# Letter", fr)

    c, user = auth_user
    from app.db.models import AnschreibenVariant, CVVariant
    cv = db_session.query(CVVariant).filter_by(user_id=user.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=user.id).first()
    aid = c.post(
        "/api/applications",
        json={
            "url": "https://x.test/c",
            "cv_variant_id": str(cv.id),
            "anschreiben_variant_id": str(an.id),
        },
    ).json()["id"]
    c.post(f"/api/applications/{aid}/generate")
    r = c.patch(
        f"/api/applications/{aid}/job-posting",
        json={"contact": {"name": "Jane", "role": None, "email": "jane@acme.test", "phone": None}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["job_posting"]["contact"]["email"] == "jane@acme.test"
    assert r.json()["job_posting_dirty"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run (sandbox OFF): `cd backend && pytest tests/integration/test_jobposting_patch.py::test_patch_contact_only_keeps_dirty_false_after_generate -v`
Expected: FAIL — `job_posting_dirty` is `True` (current code flags any update).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/api/applications.py`, `patch_job_posting`, replace the update/dirty block (currently lines 368-372):

```python
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(app_row.job_posting, k, v)
    non_contact = {k for k in updates if k != "contact"}
    if app_row.generated_md is not None and non_contact:
        app_row.job_posting_dirty = True
```

- [ ] **Step 4: Run tests to verify pass (incl. existing regression)**

Run (sandbox OFF): `cd backend && pytest tests/integration/test_jobposting_patch.py -v`
Expected: PASS — new test passes; `test_patch_job_posting_sets_dirty_after_generate` (non-contact field still flags dirty) still passes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/applications.py backend/tests/integration/test_jobposting_patch.py
git commit -m "fix(applications): contact-only patch does not flag posting dirty"
```

---

### Task 2: Frontend — make ContactBlock editable

**Files:**
- Modify: `frontend/src/components/ContactBlock.tsx` (full rewrite)

`ContactBlock` is only consumed by `JobPostingPanel` (verified: no other importers). It currently returns `null` when empty, which is exactly what blocks adding a missing email. Convert it to a controlled, always-rendered editable block.

- [ ] **Step 1: Rewrite the component**

Replace the entire contents of `frontend/src/components/ContactBlock.tsx`:

```tsx
import type { JobPosting } from "../api/applications";

type Contact = NonNullable<JobPosting["contact"]>;
type ContactField = keyof Contact;

type Props = {
  contact: JobPosting["contact"];
  disabled?: boolean;
  onChange: (field: ContactField, value: string | null) => void;
};

const FIELDS: Array<{ key: ContactField; label: string; type?: string }> = [
  { key: "name", label: "Name" },
  { key: "role", label: "Role" },
  { key: "email", label: "Email", type: "email" },
  { key: "phone", label: "Phone", type: "tel" },
];

export function ContactBlock({ contact, disabled, onChange }: Props) {
  return (
    <div className="mb-3">
      <label className="block text-xs uppercase text-slate-500">Contact</label>
      <div className="grid grid-cols-2 gap-2">
        {FIELDS.map((f) => (
          <input
            key={f.key}
            type={f.type ?? "text"}
            placeholder={f.label}
            disabled={disabled}
            value={contact?.[f.key] ?? ""}
            onChange={(e) => onChange(f.key, e.target.value || null)}
            className="border rounded px-2 py-1 text-sm"
          />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run (sandbox OFF, raw node): `cd frontend && npx tsc -b`
Expected: FAIL — `JobPostingPanel.tsx:64` still calls `<ContactBlock contact={jp.contact} />` without the new required `onChange` prop. This is fixed in Task 3. (If you prefer a green checkpoint per task, do Tasks 2 and 3 before committing — see Task 3 Step 4.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ContactBlock.tsx
git commit -m "feat(contact): make ContactBlock an editable controlled block"
```

---

### Task 3: Frontend — wire nested contact draft in JobPostingPanel

**Files:**
- Modify: `frontend/src/components/JobPostingPanel.tsx`

- [ ] **Step 1: Add contact helpers**

In `frontend/src/components/JobPostingPanel.tsx`, after the existing `value` helper (currently ends at line 60), add:

```tsx
  const contactValue = (field: keyof NonNullable<JobPosting["contact"]>): string =>
    (draft.contact?.[field] ?? jp.contact?.[field]) ?? "";

  const updateContact = (
    field: keyof NonNullable<JobPosting["contact"]>,
    val: string | null,
  ) => {
    const base = draft.contact ?? jp.contact ?? { name: null, role: null, email: null, phone: null };
    setDraft((d) => ({ ...d, contact: { ...base, [field]: val } }));
    setDirty(true);
  };
```

Note: `contactValue` is provided for parity with the other fields; `ContactBlock` reads the merged contact directly via the prop in the next step, so `contactValue` may be unused. If `tsc` flags it as unused, delete it.

- [ ] **Step 2: Pass merged contact + onChange to ContactBlock**

Replace the existing render line (currently line 64):

```tsx
      <ContactBlock contact={jp.contact} />
```

with:

```tsx
      <ContactBlock
        contact={draft.contact ?? jp.contact}
        disabled={disabled}
        onChange={updateContact}
      />
```

- [ ] **Step 3: Verify save path (read-only check, no code change)**

Confirm the existing `save` mutation already sends the whole draft:
`mutationFn: () => applications.patchJobPosting(appId, draft)` — so `{ contact }` rides along. Confirm `onSuccess` invalidates `["application", appId]`. No change needed.

- [ ] **Step 4: Typecheck**

Run (sandbox OFF, raw node): `cd frontend && npx tsc -b`
Expected: PASS — `ContactBlock` now receives all required props; `JobPosting` import already present at the top of the file.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/JobPostingPanel.tsx
git commit -m "feat(contact): edit contact fields in JobPostingPanel"
```

---

### Task 4: Frontend — modal prefers typed recipient + writes it back

**Files:**
- Modify: `frontend/src/components/InteractionLogModal.tsx`

- [ ] **Step 1: Add the writeback mutation**

In `frontend/src/components/InteractionLogModal.tsx`, after the existing `draft` mutation (ends line 67), add a mutation that overwrites the posting's contact email:

```tsx
  const saveContactEmail = useMutation({
    mutationFn: (email: string) => {
      const cur = app?.job_posting?.contact ?? {
        name: null, role: null, email: null, phone: null,
      };
      return applications.patchJobPosting(appId, { contact: { ...cur, email } });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["application", appId] });
    },
  });
```

- [ ] **Step 2: Trigger writeback on interaction-create success**

In the existing `create` mutation `onSuccess` (currently lines 45-55), persist the typed email before the reset/close branch. Capture the email first because `reset()` clears `contactHandle`. Replace the `onSuccess` body with:

```tsx
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["application-timeline", appId] });
      qc.invalidateQueries({ queryKey: ["interactions", appId] });
      const email = contactHandle.trim();
      if (channel === "mail" && direction === "out" && email && app?.job_posting) {
        saveContactEmail.mutate(email);
      }
      if (r.suggest_discard) {
        setPendingDiscardIid(r.suggest_discard.interaction_id);
        setShowDiscard(true);
      } else {
        reset();
        onClose();
      }
    },
```

- [ ] **Step 3: Recipient prefers the typed value**

Replace the stored-only recipient (currently line 89):

```tsx
  const recipient = app?.job_posting?.contact?.email ?? null;
```

with:

```tsx
  const recipient =
    contactHandle.trim() || (app?.job_posting?.contact?.email ?? null);
```

`recipient` is already used by both the `mailto(recipient, …)` href and the link's enabled/disabled styling (lines 159-163), so both now honor the typed value. The block is mail + outgoing only, so `contactHandle` is an email here.

- [ ] **Step 4: Surface writeback errors without blocking**

After the existing `draft.isError` span (currently lines 166-170), add an inline best-effort error (the interaction is already saved):

```tsx
                {saveContactEmail.isError && (
                  <span className="text-amber-600 text-xs self-center">
                    saved interaction; contact not updated
                  </span>
                )}
```

- [ ] **Step 5: Typecheck**

Run (sandbox OFF, raw node): `cd frontend && npx tsc -b`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/InteractionLogModal.tsx
git commit -m "feat(interaction): mail uses typed recipient and saves it to posting"
```

---

### Task 5: Manual verification against the Docker image

**Files:** none (verification only).

Automated frontend/UI testing is unavailable here (Playwright SIGSEGVs in the sandbox). Verify the real app. Ask the human to rebuild the image (build is blocked in-harness), then bring local images up with `--no-deps`.

- [ ] **Step 1: Rebuild + run** — human rebuilds the frontend/backend image and starts the stack.

- [ ] **Step 2: Panel add-email** — open an application whose posting has no contact email. In the job-posting panel, the Contact block now shows empty Name/Role/Email/Phone inputs. Type an email, click **Save changes**. Reload: the email persists, and the app is NOT flagged dirty/needs-regenerate by this edit alone.

- [ ] **Step 3: Modal live mailto** — open **Log interaction**, channel `mail`, direction `out`. Type an email in the "email / URL / phone" field. "Open in mail" becomes enabled immediately (before saving) and opens the mail client addressed to that email.

- [ ] **Step 4: Modal writeback** — with the above still set, click **Save**. Reopen the application's posting panel: the typed email now appears on the contact (overwriting any previous value).

- [ ] **Step 5: Draft still works without email** — on an application with no contact email, "Draft inquiry" remains enabled (pipeline-ready) and produces subject/body; recipient may be empty until set.

- [ ] **Step 6: Report** results back; no commit.

---

## Self-Review

- **Spec coverage:** Add/edit contact in panel → Tasks 2-3. Add/edit during log-interaction + live mailto + writeback → Task 4. Always-overwrite → Task 4 Step 2/1. Prefer-typed recipient → Task 4 Step 3. Dirty-flag guard → Task 1. Frontend-only/no new endpoint/no migration → honored (only `patchJobPosting` reused). Manual verification per memory constraints → Task 5.
- **Placeholders:** none — every code step shows full code; the only conditional ("delete `contactValue` if unused") is explicit, not a TODO.
- **Type consistency:** `ContactBlock` props `{ contact, disabled, onChange }` defined in Task 2 match the call site in Task 3. `patchJobPosting(appId, { contact })` matches the existing client signature and the `JobPosting.contact` shape `{name, role, email, phone}`. `recipient` reused by existing `mailto`/link code unchanged.
- **Sequencing note:** Task 2 alone leaves `tsc` red (call site not yet updated); Task 3 restores green. Acceptable as separate commits, or combine the two commits if a green checkpoint per commit is required.
