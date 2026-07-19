// Maps a machine reason code from the posting checker to a German label for
// the suggestions inbox. Keyword hits share one generic label; unknown codes
// fall back to a neutral phrase.
const REASON_LABELS: Record<string, string> = {
  http_404: "Seite nicht gefunden",
  http_403: "Zugriff verweigert",
  http_410: "Anzeige entfernt",
  redirect_root: "Weiterleitung zur Startseite",
  redirect_offhost: "Weiterleitung zu anderer Seite",
  llm_inactive: "Vermutlich nicht mehr aktiv",
};

export function suggestionReasonLabel(reason: string | null): string {
  if (!reason) return "Offline";
  if (reason.startsWith("keyword:")) return "Stelle besetzt oder abgelaufen";
  return REASON_LABELS[reason] ?? "Offline";
}
