# Frontend Refresh: Dark Theme + Mobile UX — Design

Date: 2026-07-12
Status: Approved (design)

## Goal

Make the Applicator frontend more visually appealing and usable on mobile
phones. Two source tasks from `open_tasks.txt`:

- Make the general frontend more appealing / nicer to use
- Optimize the user experience on mobile devices

This is a **visual and layout refresh only**. No feature behavior changes.
Multiple-interview tracking (also in `open_tasks.txt`) is a separate feature
with its own spec and is explicitly out of scope here.

## Decisions

- **Visual direction:** Dark theme with a bright accent ("C" direction).
- **Theming:** Light + dark toggle, respecting system preference and
  remembering the user's choice.
- **Accent color:** Sky blue.
- **Mobile navigation:** Hamburger drawer on mobile; keep the top bar on desktop.
- **Implementation approach:** Design-token layer via CSS variables + Tailwind
  `darkMode: 'class'`. Zero new dependencies (matches the current lean stack).

## Current State

- React 18 + Vite + TypeScript + Tailwind (vanilla config, no theme extension).
- `App.tsx` renders a single horizontal `<Nav>` (7 links) with no responsive
  handling — it overflows on phone widths.
- `index.css` is just the three `@tailwind` directives; no tokens, no dark mode.
- Pages: `ApplicationsList`, `ApplicationDetail`, `Stats`, `Login`, several
  Settings pages. Components include `StatusBadge` (with `STATUS_HEX`), modals,
  panels.
- Charts use `recharts`. Existing Playwright e2e suite covers key flows.

## Architecture

### 1. Theming tokens

`index.css` defines semantic CSS variables:

- `:root` holds light-theme values.
- `.dark` overrides with dark-theme values.

Token set: `--bg`, `--surface`, `--surface-2`, `--text`, `--text-muted`,
`--border`, `--accent`, `--accent-fg`, `--ring`.

Palette: neutral slate scale for surfaces/text, sky blue for the accent.

`tailwind.config.js`:

- `darkMode: 'class'`
- `theme.extend.colors` maps names (`bg`, `surface`, `surface-2`, `text`,
  `text-muted`, `border`, `accent`, `accent-fg`, `ring`) to
  `rgb(var(--token) / <alpha-value>)` so utilities like `bg-surface`,
  `text-text-muted`, `border-border` work in both themes.

`StatusBadge` keeps `STATUS_HEX` but gains dark-theme-aware variants so badges
stay legible on dark surfaces.

### 2. Theme toggle

- `useTheme` hook: resolves theme from `localStorage.theme`, falling back to
  `prefers-color-scheme`. Applies/removes `.dark` on `<html>`. Persists the
  user's explicit choice to `localStorage`.
- An inline script in `index.html` `<head>` applies the correct class **before
  first paint** to avoid a flash of the wrong theme.
- A sun/moon toggle button lives in the nav (both desktop and mobile).

### 3. App shell / navigation

Split the current `<Nav>` into:

- `<DesktopNav>` — the existing top bar, restyled with tokens. Active item shown
  with an accent underline. Visible at `md:` and up.
- `<MobileNav>` — logo + hamburger (☰) + theme toggle. Visible below `md`.

The hamburger opens a **slide-in drawer** listing all 7 links plus logout.
Settings links are grouped under a "Settings" subheading. Drawer is accessible:

- Focus trap while open.
- Close on Esc, overlay click, and link navigation.
- `aria-expanded` / `aria-controls` on the toggle button.

### 4. Component primitives & page refresh

New `components/ui/` primitives:

- `Button` — variants: primary / secondary / ghost / danger.
- `Card` — token-based surface container.
- `IconButton` — for the toggle and drawer controls.

Refactor high-traffic shared surfaces to tokens + primitives:

- `ApplicationsList` — rows become cards; touch targets ≥ 44px; filter chips
  wrap cleanly.
- `ApplicationDetail` — single-column stack on mobile; side-by-side panels on
  desktop.
- `Stats` — recharts colors derived from theme tokens; charts scale to width.
- `Login`, Settings pages, and modals (`InteractionLogModal`, dialogs) — token
  pass so no surface stays white-on-dark.

Feature behavior is untouched; changes are visual/layout only.

### 5. Responsive strategy

- Mobile-first: base styles target phones; `md:` / `lg:` layer on desktop layout.
- Remove fixed widths that overflow; containers use `max-w-*` + `px-4`.
- Tap targets ≥ 44px.
- Verify at 375px, 768px, and 1280px.

## Testing

- Existing Playwright e2e suite must continue to pass.
- New coverage:
  - Theme toggle persists across reload; no flash of wrong theme on load.
  - Drawer opens/closes and is keyboard-accessible (Esc, focus trap).
  - At 375px viewport, the drawer is shown and the desktop top bar is hidden.
  - Key pages render correctly in both light and dark themes.
- Unit test for `useTheme` resolution logic (localStorage vs system preference).

## Out of Scope

- Multiple-interview tracking (separate spec).
- Any backend or data-model changes.
- New runtime dependencies.
