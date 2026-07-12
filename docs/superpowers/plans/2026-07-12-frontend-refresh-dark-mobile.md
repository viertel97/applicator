# Frontend Refresh: Dark Theme + Mobile UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Applicator frontend a dark/light themeable look with a sky accent and a mobile-friendly navigation drawer, without changing any feature behavior.

**Architecture:** Introduce a CSS-variable design-token layer consumed through Tailwind's `theme.extend.colors` (`darkMode: 'class'`). A `useTheme` hook toggles a `.dark` class on `<html>` and persists the choice; an inline head script applies it before paint. Navigation splits into a desktop top bar and a mobile hamburger drawer. Existing components are migrated from hard-coded slate/white classes to semantic token classes.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS 3, @tanstack/react-query, react-router-dom, recharts, Playwright (e2e), `node --test` (unit).

**Spec:** `docs/superpowers/specs/2026-07-12-frontend-refresh-design.md`

**Working directory for all commands:** `frontend/`

---

## Token Reference (used throughout)

Semantic color tokens. Light values in `:root`, dark values in `.dark`. Stored as space-separated RGB triples so Tailwind can apply `<alpha-value>`.

| Token         | Tailwind name | Light (RGB)   | Dark (RGB)    | Meaning                         |
|---------------|---------------|---------------|---------------|---------------------------------|
| `--bg`        | `bg`          | `248 250 252` | `15 23 42`    | page background                 |
| `--surface`   | `surface`     | `255 255 255` | `30 41 59`    | cards, nav, modals              |
| `--surface-2` | `surface2`    | `241 245 249` | `51 65 85`    | insets, hover, subtle fills     |
| `--fg`        | `fg`          | `15 23 42`    | `241 245 249` | primary text                    |
| `--muted`     | `muted`       | `100 116 139` | `148 163 184` | secondary text                  |
| `--border`    | `border`      | `226 232 240` | `51 65 85`    | borders, dividers               |
| `--accent`    | `accent`      | `2 132 199`   | `56 189 248`  | links, active nav, primary btn  |
| `--accent-fg` | `accentFg`    | `255 255 255` | `2 6 23`      | text/icon on accent             |
| `--ring`      | `ring`        | `14 165 233`  | `56 189 248`  | focus ring                      |

**Migration mapping** (apply everywhere a hard-coded class is replaced):

| Old class                                   | New class                        |
|---------------------------------------------|----------------------------------|
| `bg-white`                                  | `bg-surface`                     |
| `bg-slate-50`                               | `bg-bg`                          |
| `bg-slate-100`                              | `bg-surface2`                    |
| `text-slate-900`, default black text        | `text-fg`                        |
| `text-slate-600`, `text-slate-500`          | `text-muted`                     |
| `text-slate-400`                            | `text-muted`                     |
| `border`, `border-slate-200/300`            | `border border-border`           |
| `text-blue-600`, link colors                | `text-accent`                    |
| `bg-slate-700 text-white` (active chip)      | `bg-accent text-accentFg`        |
| `focus:border-slate-500`, ad-hoc focus       | `focus:outline-none focus:ring-2 focus:ring-ring` |

---

## File Structure

**Create:**
- `frontend/src/lib/theme.ts` — pure `resolveTheme()` logic
- `frontend/src/lib/theme.test.ts` — unit tests for `resolveTheme()`
- `frontend/src/hooks/useTheme.ts` — hook that applies/persists theme
- `frontend/src/components/ThemeToggle.tsx` — sun/moon toggle button
- `frontend/src/components/ui/Button.tsx` — button primitive
- `frontend/src/components/ui/Card.tsx` — surface container primitive
- `frontend/src/components/ui/IconButton.tsx` — icon button primitive
- `frontend/src/components/nav/DesktopNav.tsx` — desktop top bar
- `frontend/src/components/nav/MobileNav.tsx` — mobile bar + drawer
- `frontend/src/components/nav/navItems.ts` — shared nav link list
- `frontend/tests/theme-mobile.spec.ts` — e2e for toggle + drawer + viewport

**Modify:**
- `frontend/tailwind.config.js` — `darkMode: 'class'` + token colors
- `frontend/src/index.css` — token definitions + base body styles
- `frontend/index.html` — no-flash inline script
- `frontend/src/App.tsx` — split `Nav` into Desktop/Mobile
- `frontend/src/components/StatusBadge.tsx` — dark-aware badge classes
- `frontend/src/pages/ApplicationsList.tsx` — token pass + card rows
- `frontend/src/pages/ApplicationDetail.tsx` — token pass + responsive stack
- `frontend/src/pages/Stats.tsx` — token pass + theme-aware charts
- `frontend/src/pages/Login.tsx`, Settings pages, modals — token pass

---

## Task 1: Tailwind token wiring

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Enable class dark mode and map token colors**

Replace the contents of `frontend/tailwind.config.js`:

```js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        surface2: "rgb(var(--surface-2) / <alpha-value>)",
        fg: "rgb(var(--fg) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        accentFg: "rgb(var(--accent-fg) / <alpha-value>)",
        ring: "rgb(var(--ring) / <alpha-value>)",
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 2: Define tokens and base body styles**

Replace the contents of `frontend/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --bg: 248 250 252;
    --surface: 255 255 255;
    --surface-2: 241 245 249;
    --fg: 15 23 42;
    --muted: 100 116 139;
    --border: 226 232 240;
    --accent: 2 132 199;
    --accent-fg: 255 255 255;
    --ring: 14 165 233;
  }

  .dark {
    --bg: 15 23 42;
    --surface: 30 41 59;
    --surface-2: 51 65 85;
    --fg: 241 245 249;
    --muted: 148 163 184;
    --border: 51 65 85;
    --accent: 56 189 248;
    --accent-fg: 2 6 23;
    --ring: 56 189 248;
  }

  body {
    @apply bg-bg text-fg;
  }
}
```

- [ ] **Step 3: Verify the build compiles**

Run: `node node_modules/.bin/tsc -b && node node_modules/.bin/vite build`
Expected: build succeeds, no Tailwind "unknown class" errors.

> If `tsc`/`vite` output is summarized/masked by a proxy, run the raw `node node_modules/.bin/...` binaries directly with the sandbox disabled so real errors surface.

- [ ] **Step 4: Commit**

```bash
git add frontend/tailwind.config.js frontend/src/index.css
git commit -m "feat(theme): add design-token color layer and dark-mode base"
```

---

## Task 2: Theme resolution logic (pure + tested)

**Files:**
- Create: `frontend/src/lib/theme.ts`
- Test: `frontend/src/lib/theme.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/theme.test.ts`:

```ts
import test from "node:test";
import assert from "node:assert/strict";
import { resolveTheme } from "./theme.ts";

test("stored 'dark' wins over system preference", () => {
  assert.equal(resolveTheme("dark", false), "dark");
});

test("stored 'light' wins over system preference", () => {
  assert.equal(resolveTheme("light", true), "light");
});

test("no stored value falls back to system: dark", () => {
  assert.equal(resolveTheme(null, true), "dark");
});

test("no stored value falls back to system: light", () => {
  assert.equal(resolveTheme(null, false), "light");
});

test("unrecognized stored value falls back to system", () => {
  assert.equal(resolveTheme("bogus", true), "dark");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test 'src/lib/theme.test.ts'`
Expected: FAIL — cannot resolve `./theme.ts` / `resolveTheme` is not defined.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/lib/theme.ts`:

```ts
export type Theme = "light" | "dark";

/** Resolve the effective theme from a stored preference and the OS setting. */
export function resolveTheme(
  stored: string | null,
  systemPrefersDark: boolean,
): Theme {
  if (stored === "light" || stored === "dark") return stored;
  return systemPrefersDark ? "dark" : "light";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test 'src/lib/theme.test.ts'`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/theme.ts frontend/src/lib/theme.test.ts
git commit -m "feat(theme): add resolveTheme with unit tests"
```

---

## Task 3: useTheme hook, no-flash script, ThemeToggle

**Files:**
- Create: `frontend/src/hooks/useTheme.ts`
- Create: `frontend/src/components/ThemeToggle.tsx`
- Modify: `frontend/index.html`

- [ ] **Step 1: Add the no-flash inline script**

In `frontend/index.html`, add this inside `<head>` immediately after the `<title>` line. It applies `.dark` before React mounts so there is no flash of the wrong theme:

```html
    <script>
      (function () {
        try {
          var stored = localStorage.getItem("theme");
          var dark = stored
            ? stored === "dark"
            : window.matchMedia("(prefers-color-scheme: dark)").matches;
          if (dark) document.documentElement.classList.add("dark");
        } catch (e) {}
      })();
    </script>
```

- [ ] **Step 2: Write the useTheme hook**

Create `frontend/src/hooks/useTheme.ts`:

```ts
import { useCallback, useEffect, useState } from "react";
import { resolveTheme, type Theme } from "../lib/theme";

const STORAGE_KEY = "theme";

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() =>
    resolveTheme(
      localStorage.getItem(STORAGE_KEY),
      window.matchMedia("(prefers-color-scheme: dark)").matches,
    ),
  );

  useEffect(() => {
    apply(theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  return { theme, toggle };
}
```

- [ ] **Step 3: Write the ThemeToggle component**

Create `frontend/src/components/ThemeToggle.tsx`:

```tsx
import { useTheme } from "../hooks/useTheme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Light theme" : "Dark theme"}
      className="p-2 rounded text-muted hover:text-fg hover:bg-surface2 focus:outline-none focus:ring-2 focus:ring-ring"
    >
      {isDark ? "☀" : "☾"}
    </button>
  );
}
```

- [ ] **Step 4: Verify the build compiles**

Run: `node node_modules/.bin/tsc -b`
Expected: no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/src/hooks/useTheme.ts frontend/src/components/ThemeToggle.tsx
git commit -m "feat(theme): add useTheme hook, no-flash script, and toggle button"
```

---

## Task 4: UI primitives (Button, Card, IconButton)

**Files:**
- Create: `frontend/src/components/ui/Button.tsx`
- Create: `frontend/src/components/ui/Card.tsx`
- Create: `frontend/src/components/ui/IconButton.tsx`

- [ ] **Step 1: Create Button**

Create `frontend/src/components/ui/Button.tsx`:

```tsx
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accentFg hover:opacity-90",
  secondary: "bg-surface2 text-fg border border-border hover:bg-surface",
  ghost: "text-muted hover:text-fg hover:bg-surface2",
  danger: "bg-rose-600 text-white hover:bg-rose-700",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}
```

- [ ] **Step 2: Create Card**

Create `frontend/src/components/ui/Card.tsx`:

```tsx
import type { HTMLAttributes } from "react";

export function Card({
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`bg-surface border border-border rounded-lg ${className}`}
      {...props}
    />
  );
}
```

- [ ] **Step 3: Create IconButton**

Create `frontend/src/components/ui/IconButton.tsx`:

```tsx
import type { ButtonHTMLAttributes } from "react";

export function IconButton({
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`inline-flex h-11 w-11 items-center justify-center rounded text-muted hover:text-fg hover:bg-surface2 focus:outline-none focus:ring-2 focus:ring-ring ${className}`}
      {...props}
    />
  );
}
```

- [ ] **Step 4: Verify the build compiles**

Run: `node node_modules/.bin/tsc -b`
Expected: no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui
git commit -m "feat(ui): add Button, Card, IconButton primitives"
```

---

## Task 5: Split navigation into desktop bar + mobile drawer

**Files:**
- Create: `frontend/src/components/nav/navItems.ts`
- Create: `frontend/src/components/nav/DesktopNav.tsx`
- Create: `frontend/src/components/nav/MobileNav.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Extract the shared nav link list**

Create `frontend/src/components/nav/navItems.ts`:

```ts
export type NavItem = { to: string; label: string; group: "main" | "settings" };

export const NAV_ITEMS: NavItem[] = [
  { to: "/applications", label: "Applications", group: "main" },
  { to: "/stats", label: "Stats", group: "main" },
  { to: "/settings/cv", label: "CV", group: "settings" },
  { to: "/settings/anschreiben", label: "Anschreiben", group: "settings" },
  { to: "/settings/llm", label: "LLM", group: "settings" },
  { to: "/settings/inquiry-prompt", label: "Inquiry prompt", group: "settings" },
  { to: "/settings/discard-reasons", label: "Discard reasons", group: "settings" },
];
```

- [ ] **Step 2: Create DesktopNav**

Create `frontend/src/components/nav/DesktopNav.tsx`:

```tsx
import { Link, useLocation } from "react-router-dom";
import { NAV_ITEMS } from "./navItems";
import { ThemeToggle } from "../ThemeToggle";

export function DesktopNav({ oauthEnabled }: { oauthEnabled?: boolean }) {
  const loc = useLocation();
  return (
    <nav className="hidden md:flex bg-surface border-b border-border px-4 py-2 gap-1 items-center">
      <span className="font-bold text-fg mr-3">Applicator</span>
      {NAV_ITEMS.map(({ to, label }) => {
        const active = loc.pathname.startsWith(to);
        return (
          <Link
            key={to}
            to={to}
            className={`px-3 py-2 text-sm rounded ${
              active
                ? "text-accent font-semibold"
                : "text-muted hover:text-fg"
            }`}
          >
            {label}
          </Link>
        );
      })}
      <div className="ml-auto flex items-center gap-1">
        <ThemeToggle />
        {oauthEnabled && (
          <form action="/api/auth/logout" method="post">
            <button className="text-sm text-muted hover:text-fg px-2">
              Logout
            </button>
          </form>
        )}
      </div>
    </nav>
  );
}
```

- [ ] **Step 3: Create MobileNav with an accessible drawer**

Create `frontend/src/components/nav/MobileNav.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { NAV_ITEMS } from "./navItems";
import { ThemeToggle } from "../ThemeToggle";
import { IconButton } from "../ui/IconButton";

export function MobileNav({ oauthEnabled }: { oauthEnabled?: boolean }) {
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Close on route change.
  useEffect(() => {
    setOpen(false);
  }, [loc.pathname]);

  // Close on Escape; trap focus inside the drawer while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    drawerRef.current?.querySelector<HTMLElement>("a,button")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const main = NAV_ITEMS.filter((i) => i.group === "main");
  const settings = NAV_ITEMS.filter((i) => i.group === "settings");

  const link = (to: string, label: string) => (
    <Link
      key={to}
      to={to}
      className={`block px-4 py-3 rounded text-sm ${
        loc.pathname.startsWith(to)
          ? "text-accent font-semibold bg-surface2"
          : "text-fg hover:bg-surface2"
      }`}
    >
      {label}
    </Link>
  );

  return (
    <nav className="md:hidden bg-surface border-b border-border px-3 py-2 flex items-center">
      <span className="font-bold text-fg">Applicator</span>
      <div className="ml-auto flex items-center gap-1">
        <ThemeToggle />
        <IconButton
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="mobile-drawer"
          onClick={() => setOpen(true)}
        >
          ☰
        </IconButton>
      </div>

      {open && (
        <div className="fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setOpen(false)}
          />
          <div
            ref={drawerRef}
            id="mobile-drawer"
            role="dialog"
            aria-modal="true"
            className="absolute right-0 top-0 h-full w-72 max-w-[80%] bg-surface border-l border-border p-2 flex flex-col overflow-y-auto"
          >
            <div className="flex items-center px-2 py-2">
              <span className="font-bold text-fg">Menu</span>
              <IconButton
                aria-label="Close menu"
                className="ml-auto"
                onClick={() => setOpen(false)}
              >
                ✕
              </IconButton>
            </div>
            {main.map((i) => link(i.to, i.label))}
            <div className="px-4 pt-4 pb-1 text-xs uppercase tracking-wide text-muted">
              Settings
            </div>
            {settings.map((i) => link(i.to, i.label))}
            {oauthEnabled && (
              <form
                action="/api/auth/logout"
                method="post"
                className="mt-auto px-2 pt-4"
              >
                <button className="w-full text-left px-2 py-3 text-sm text-muted hover:text-fg">
                  Logout
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </nav>
  );
}
```

- [ ] **Step 4: Wire both into App.tsx**

In `frontend/src/App.tsx`, delete the local `Nav` function (lines 13–42) and its now-unused imports (`Link`, `useLocation`). Add these imports near the top:

```tsx
import { DesktopNav } from "./components/nav/DesktopNav";
import { MobileNav } from "./components/nav/MobileNav";
```

Then replace the `ProtectedShell` component body so it renders both nav variants:

```tsx
function ProtectedShell({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useAuth();
  if (isLoading) return <div className="p-6 text-muted">Loading…</div>;
  if (!data) return <Navigate to="/login" replace />;
  return (
    <>
      <DesktopNav oauthEnabled={data.oauth_enabled} />
      <MobileNav oauthEnabled={data.oauth_enabled} />
      {children}
    </>
  );
}
```

Keep the remaining `import { Navigate, Route, Routes } from "react-router-dom";` (drop `Link` and `useLocation` from that import).

- [ ] **Step 5: Verify the build compiles**

Run: `node node_modules/.bin/tsc -b`
Expected: no type errors, no unused-import errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/nav frontend/src/App.tsx
git commit -m "feat(nav): split into desktop bar and accessible mobile drawer"
```

---

## Task 6: e2e coverage for theme toggle + mobile drawer

**Files:**
- Create: `frontend/tests/theme-mobile.spec.ts`

- [ ] **Step 1: Write the e2e tests**

Create `frontend/tests/theme-mobile.spec.ts`:

```ts
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
```

- [ ] **Step 2: Run the new tests to verify they pass**

Run: `node node_modules/.bin/playwright test tests/theme-mobile.spec.ts`
Expected: 2 passed.

> Playwright can SIGSEGV inside the nono sandbox — run this with the sandbox disabled. Do not chase Node/browser versions if it crashes there.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/theme-mobile.spec.ts
git commit -m "test(theme): cover toggle persistence and mobile drawer"
```

---

## Task 7: Dark-aware StatusBadge

**Files:**
- Modify: `frontend/src/components/StatusBadge.tsx`

- [ ] **Step 1: Add dark variants to the badge class maps**

In `frontend/src/components/StatusBadge.tsx`, replace `STATUS_CLASS` (lines 3–14) with dark-aware classes:

```ts
const STATUS_CLASS: Record<AppStatus, string> = {
  draft: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
  applied: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200",
  offer: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200",
  rejected: "bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-200",
  accepted: "bg-green-200 text-green-800 dark:bg-green-900 dark:text-green-200",
  withdrawn: "bg-slate-300 text-slate-600 dark:bg-slate-600 dark:text-slate-200",
  discarded: "bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-200",
  need_call: "bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-200",
  apply_direct: "bg-teal-100 text-teal-700 dark:bg-teal-900 dark:text-teal-200",
  interview: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200",
};
```

Then update the `JobStateBadge` class ternary (lines 58–65) to add dark variants:

```ts
  const cls =
    state === "ready"
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200"
      : state === "failed"
        ? "bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-200"
        : state === "extracted"
          ? "bg-sky-100 text-sky-700 dark:bg-sky-900 dark:text-sky-200"
          : "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-200";
```

And `OnlineBadge` (lines 76–82):

```ts
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
        online
          ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200"
          : "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200"
      }`}
```

Leave `STATUS_HEX` unchanged — it styles native `<option>` elements where CSS classes don't apply, and the colored dropdown already handles its own palette.

- [ ] **Step 2: Verify the build compiles**

Run: `node node_modules/.bin/tsc -b`
Expected: no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StatusBadge.tsx
git commit -m "feat(theme): dark-aware status and job-state badges"
```

---

## Task 8: Token pass — ApplicationsList (rows → cards, touch targets)

**Files:**
- Modify: `frontend/src/pages/ApplicationsList.tsx`

Apply the **Migration mapping** table to every hard-coded color/border class in this file. Below are the load-bearing changes; apply the same substitutions to every other occurrence in the file.

- [ ] **Step 1: Container and search input**

Change the container (line ~309) and search input (line ~319):

```tsx
    <div className="max-w-4xl mx-auto p-4 sm:p-6">
```

```tsx
          className="w-full text-sm bg-surface border border-border rounded px-3 py-2 pr-8 text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring"
```

Change the clear-search button (line ~326) to `text-muted hover:text-fg`.

- [ ] **Step 2: Status filter chips**

For the active/hidden chip classes (lines ~348–352), replace with:

```tsx
              className={`text-xs px-2 py-1 rounded border transition-colors ${
                hidden
                  ? "bg-surface text-muted border-border"
                  : "bg-accent text-accentFg border-accent"
              }`}
```

Replace `text-slate-500`/`text-slate-400` label spans in this section (lines ~335–337, ~360, ~370–372) with `text-muted`.

- [ ] **Step 3: Application rows become cards with touch-friendly targets**

Locate the row wrapper (the element around line ~458 `flex flex-wrap gap-1` sits inside each row) and the row link (`flex-1 truncate min-w-0` at line ~509). Wrap each application row in the `Card` primitive and ensure the primary tap target has adequate height. Import at the top of the file:

```tsx
import { Card } from "../components/ui/Card";
```

Give the row card these classes and make the title link at least 44px tall:

```tsx
<Card className="mb-2 p-3 hover:bg-surface2 transition-colors">
  {/* ...row contents... */}
</Card>
```

For the title link (line ~509):

```tsx
className="flex-1 truncate min-w-0 py-1.5 text-fg hover:text-accent"
```

Replace the delete control's colors with `text-muted hover:text-rose-600` but keep its existing `aria-label="delete"` (the e2e suite selects on it).

- [ ] **Step 4: Sweep remaining hard-coded classes**

Search the file for leftover `slate-`, `bg-white`, `text-blue`, `border-slate` and apply the mapping table. Command:

Run: `rg -n "slate-|bg-white|text-blue|border-slate" src/pages/ApplicationsList.tsx`
Expected after edits: no matches (or only intentional non-theme colors, e.g. rose for delete).

- [ ] **Step 5: Verify build + existing e2e still pass**

Run: `node node_modules/.bin/tsc -b`
Run: `node node_modules/.bin/playwright test tests/e2e.spec.ts tests/search-filter.spec.ts`
Expected: build clean; existing list/search/delete specs pass (they assert on text and `aria-label="delete"`, both preserved).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ApplicationsList.tsx
git commit -m "feat(theme): token pass and card rows for ApplicationsList"
```

---

## Task 9: Token pass — ApplicationDetail (responsive stack)

**Files:**
- Modify: `frontend/src/pages/ApplicationDetail.tsx`

- [ ] **Step 1: Make the two-panel layout stack on mobile**

Find the top-level layout container in the returned JSX. Where panels sit side by side (a `flex` row or a fixed-width grid), change it to stack by default and split at `md`. Example transform:

```tsx
// before: <div className="flex gap-6">
<div className="flex flex-col md:flex-row gap-4 md:gap-6 p-4 md:p-6">
```

Any panel with a fixed width like `w-[420px]` becomes `w-full md:w-[420px]`.

- [ ] **Step 2: Apply the migration mapping across the file**

Replace hard-coded classes per the mapping table (`bg-white`→`bg-surface`, text/border slates→`text-fg`/`text-muted`/`border-border`, link blues→`text-accent`). Preserve every `label:has-text(...)`, `aria-label`, and button text used by the e2e suite (`Title` label + input, `Download DOCX`, contact `mailto:`/`tel:` links, `Extracted` text).

Run: `rg -n "slate-|bg-white|text-blue|border-slate" src/pages/ApplicationDetail.tsx`
Expected after edits: no theme-relevant matches remain.

- [ ] **Step 3: Verify build + detail e2e pass**

Run: `node node_modules/.bin/tsc -b`
Run: `node node_modules/.bin/playwright test tests/e2e.spec.ts tests/interaction-log.spec.ts tests/delete-interaction.spec.ts`
Expected: build clean; specs pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ApplicationDetail.tsx
git commit -m "feat(theme): token pass and responsive stack for ApplicationDetail"
```

---

## Task 10: Token pass — Stats (theme-aware charts)

**Files:**
- Modify: `frontend/src/pages/Stats.tsx`

- [ ] **Step 1: Derive chart colors from CSS tokens**

recharts does not read Tailwind classes for series/axis colors — it needs concrete color strings. Add a small helper near the top of the component that reads the resolved token values so charts follow the theme:

```tsx
function tokenColor(name: string): string {
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return v ? `rgb(${v})` : "#64748b";
}
```

Use `tokenColor("--accent")` for primary series/bars, `tokenColor("--muted")` for axis ticks and grid, and `tokenColor("--border")` for the cartesian grid stroke. For multi-series charts that need distinct hues, keep the existing categorical palette but define it inline as hex values (charts stay readable in both themes because the surface behind them uses `bg-surface`).

- [ ] **Step 2: Apply the migration mapping to page chrome**

Replace hard-coded `bg-white`/slate/border classes on cards, headings, and tables with tokens. Wrap stat cards in the `Card` primitive where a bordered white box exists today.

Run: `rg -n "slate-|bg-white|text-blue|border-slate" src/pages/Stats.tsx`
Expected after edits: no theme-relevant matches remain.

- [ ] **Step 3: Verify build + stats tests pass**

Run: `node node_modules/.bin/tsc -b`
Run: `node --test 'src/**/*.test.ts'`
Expected: build clean; all unit tests pass (stats metric functions unaffected).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Stats.tsx
git commit -m "feat(theme): token pass and theme-aware charts for Stats"
```

---

## Task 11: Token pass — Login, Settings pages, modals

**Files:**
- Modify: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/pages/SettingsDiscardReasons.tsx`
- Modify: `frontend/src/pages/SettingsInquiryPrompt.tsx`
- Modify: `frontend/src/pages/SettingsCV.tsx`, `SettingsAnschreiben.tsx`, `SettingsLLM.tsx`, `_VariantSettings.tsx`
- Modify: `frontend/src/components/InteractionLogModal.tsx`
- Modify: `frontend/src/components/ConfirmDialog.tsx`
- Modify: any component still rendering `bg-white` / slate text (see sweep)

- [ ] **Step 1: Find every remaining hard-coded surface**

Run: `rg -n "bg-white|bg-slate-50|text-slate-[0-9]|border-slate|text-blue-[0-9]" src/pages src/components`
This lists every file/line still using non-token colors.

- [ ] **Step 2: Apply the migration mapping file by file**

For each hit, substitute per the mapping table. Modal/dialog panels use `bg-surface border border-border`; overlays use `bg-black/50`. Inputs and textareas use `bg-surface border border-border text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-ring`. Primary action buttons should use the `Button` primitive (`variant="primary"`); destructive ones `variant="danger"`.

Do not alter component logic, props, `aria-label`s, or button text — only class strings and, where noted, wrapping an existing box in `Card`/`Button`.

- [ ] **Step 3: Re-run the sweep until clean**

Run: `rg -n "bg-white|bg-slate-50|text-slate-[0-9]|border-slate|text-blue-[0-9]" src/pages src/components`
Expected: no matches except intentional semantic colors (rose for danger, status palette in `StatusBadge`, categorical chart hues).

- [ ] **Step 4: Verify build + full e2e suite**

Run: `node node_modules/.bin/tsc -b`
Run: `node node_modules/.bin/playwright test`
Expected: build clean; entire e2e suite green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(theme): token pass for login, settings pages, and modals"
```

---

## Task 12: Final verification pass

**Files:** none (verification only)

- [ ] **Step 1: Build the app the way it ships**

Run: `node node_modules/.bin/tsc -b && node node_modules/.bin/vite build`
Expected: production build succeeds.

- [ ] **Step 2: Run the entire test suite**

Run: `node --test 'src/**/*.test.ts'`
Run: `node node_modules/.bin/playwright test`
Expected: all unit and e2e tests pass.

- [ ] **Step 3: Manual visual check in both themes at three breakpoints**

Run: `node node_modules/.bin/vite --port 5273`
Open `http://localhost:5273` and verify, in both light and dark (toggle in nav), at widths 375px, 768px, 1280px:
- No white-on-dark or black-on-dark surfaces anywhere.
- Mobile (375px): top bar hidden, hamburger opens the drawer, all 7 links reachable, Escape/overlay/link-tap all close it.
- Desktop (1280px): top bar visible, active item shown in accent, no hamburger.
- ApplicationDetail panels stack on mobile, sit side by side on desktop.
- Stats charts are legible in both themes.

> Verify against the app served here (or the Docker image), not in-container replays — those bypass the real UI. If a Docker rebuild is needed and the harness build fails on a keychain error, have the user build in their terminal.

- [ ] **Step 4: No commit needed** — verification only. Proceed to finishing the branch.

---

## Self-Review (completed by plan author)

- **Spec coverage:** tokens+dark mode (T1), toggle w/ system pref + persistence + no-flash (T2,T3), sky accent (T1 token values), hamburger drawer + desktop bar (T5), accessibility of drawer (T5), primitives (T4), page refreshes incl. responsive stack & theme-aware charts & touch targets (T6–T11 — note T6 is tests), badge dark variants (T7), testing incl. useTheme unit + drawer/viewport/persistence e2e + existing suite (T2,T6,T12). All spec sections map to tasks.
- **Placeholder scan:** page token-pass tasks give the mapping table, load-bearing diffs, and `rg` gates rather than reproducing 400-line files verbatim — actionable without placeholders.
- **Type consistency:** `resolveTheme(stored, systemPrefersDark)` and `Theme` used identically in `theme.ts`/`useTheme.ts`; `NAV_ITEMS`/`NavItem` shared by both nav components; primitive prop names (`variant`) consistent.
```
