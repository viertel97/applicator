const MONTHS: Record<string, number> = {
  january: 0, february: 1, march: 2, april: 3, may: 4, june: 5,
  july: 6, august: 7, september: 8, october: 9, november: 10, december: 11,
};

const pad = (n: number) => String(n).padStart(2, "0");

// Parses a pasted calendar/date string into a `datetime-local` value
// (`YYYY-MM-DDTHH:mm`). Deterministic, no deps. Takes the start time of a
// range and assumes the current year unless the string states one.
// Returns null when the text does not match a recognizable date+time.
export function parseCalendarPaste(raw: string, now: Date = new Date()): string | null {
  const t = raw.normalize("NFKC").replace(/[\u00a0\u202f]/g, " ");
  const m = t.match(/([A-Za-z]+)\s+(\d{1,2})(?:,\s*(\d{4}))?\D*?(\d{1,2}):(\d{2})/);
  if (!m) return null;

  const mon = MONTHS[m[1].toLowerCase()];
  if (mon === undefined) return null;

  const day = Number(m[2]);
  const year = m[3] ? Number(m[3]) : now.getFullYear();
  const hh = Number(m[4]);
  const mm = Number(m[5]);
  if (day < 1 || day > 31 || hh > 23 || mm > 59) return null;

  return `${year}-${pad(mon + 1)}-${pad(day)}T${pad(hh)}:${pad(mm)}`;
}
