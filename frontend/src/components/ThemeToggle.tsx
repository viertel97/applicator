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
