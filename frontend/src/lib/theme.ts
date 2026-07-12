export type Theme = "light" | "dark";

/** Resolve the effective theme from a stored preference and the OS setting. */
export function resolveTheme(
  stored: string | null,
  systemPrefersDark: boolean,
): Theme {
  if (stored === "light" || stored === "dark") return stored;
  return systemPrefersDark ? "dark" : "light";
}
