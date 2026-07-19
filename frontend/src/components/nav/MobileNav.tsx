import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import { NAV_ITEMS } from "./navItems";
import { ThemeToggle } from "../ThemeToggle";
import { IconButton } from "../ui/IconButton";
import { NavCountBadge } from "./NavCountBadge";
import { useSuggestionsCount } from "../../hooks/useSuggestionsCount";

export function MobileNav({ oauthEnabled }: { oauthEnabled?: boolean }) {
  const loc = useLocation();
  const suggestionCount = useSuggestionsCount();
  const [open, setOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Close on route change.
  useEffect(() => {
    setOpen(false);
  }, [loc.pathname]);

  // While open: focus the first item, trap Tab within the drawer, close on
  // Escape, and lock body scroll.
  useEffect(() => {
    if (!open) return;
    const focusables = () =>
      Array.from(
        drawerRef.current?.querySelectorAll<HTMLElement>(
          "a[href],button:not([disabled])",
        ) ?? [],
      );
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key === "Tab") {
        const items = focusables();
        if (items.length === 0) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    focusables()[0]?.focus();
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open]);

  const main = NAV_ITEMS.filter((i) => i.group === "main");
  const settings = NAV_ITEMS.filter((i) => i.group === "settings");

  const link = (to: string, label: string) => (
    <Link
      key={to}
      to={to}
      className={`flex items-center gap-2 px-4 py-3 rounded text-sm ${
        loc.pathname.startsWith(to)
          ? "text-accent font-semibold bg-surface2"
          : "text-fg hover:bg-surface2"
      }`}
    >
      {label}
      {to === "/suggestions" && <NavCountBadge count={suggestionCount} />}
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
          aria-controls={open ? "mobile-drawer" : undefined}
          onClick={() => setOpen(true)}
        >
          ☰
        </IconButton>
      </div>

      {open &&
        createPortal(
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
              aria-labelledby="mobile-drawer-title"
              className="absolute right-0 top-0 h-full w-72 max-w-[80%] bg-surface border-l border-border p-2 flex flex-col overflow-y-auto"
            >
              <div className="flex items-center px-2 py-2">
                <span id="mobile-drawer-title" className="font-bold text-fg">
                  Menu
                </span>
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
          </div>,
          document.body,
        )}
    </nav>
  );
}
