import { Link, useLocation } from "react-router-dom";
import { NAV_ITEMS } from "./navItems";
import { ThemeToggle } from "../ThemeToggle";
import { NavCountBadge } from "./NavCountBadge";
import { useSuggestionsCount } from "../../hooks/useSuggestionsCount";
import { useReviewCount } from "../../hooks/useReviewCount";

export function DesktopNav({ oauthEnabled }: { oauthEnabled?: boolean }) {
  const loc = useLocation();
  const suggestionCount = useSuggestionsCount();
  const reviewCount = useReviewCount();
  return (
    <nav className="hidden md:flex bg-surface border-b border-border px-4 py-2 gap-1 items-center">
      <span className="font-bold text-fg mr-3">Applicator</span>
      {NAV_ITEMS.map(({ to, label }) => {
        const active = loc.pathname.startsWith(to);
        return (
          <Link
            key={to}
            to={to}
            className={`px-3 py-2 text-sm rounded inline-flex items-center gap-1.5 ${
              active
                ? "text-accent font-semibold"
                : "text-muted hover:text-fg"
            }`}
          >
            {label}
            {to === "/suggestions" && <NavCountBadge count={suggestionCount} />}
            {to === "/calendar" && <NavCountBadge count={reviewCount} />}
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
