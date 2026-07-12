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
