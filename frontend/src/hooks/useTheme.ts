import { useCallback, useSyncExternalStore } from "react";
import { resolveTheme, type Theme } from "../lib/theme";

const STORAGE_KEY = "theme";
const listeners = new Set<() => void>();

function current(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  listeners.forEach((l) => l());
}

// Sync the DOM class to the resolved theme once at module load. The no-flash
// inline script in index.html already does this before paint; this keeps the
// store correct if that script was skipped.
apply(
  resolveTheme(
    localStorage.getItem(STORAGE_KEY),
    window.matchMedia("(prefers-color-scheme: dark)").matches,
  ),
);

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, current, current);
  const toggle = useCallback(() => {
    const next: Theme = current() === "dark" ? "light" : "dark";
    localStorage.setItem(STORAGE_KEY, next);
    apply(next);
  }, []);
  return { theme, toggle };
}
