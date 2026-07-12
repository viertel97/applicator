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
