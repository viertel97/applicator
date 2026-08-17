import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { calendar } from "../api/calendar";
import { MonthGrid } from "../components/calendar/MonthGrid";
import { AgendaList } from "../components/calendar/AgendaList";
import { IconButton } from "../components/ui/IconButton";
import { AddInterviewDialog } from "../components/calendar/AddInterviewDialog";

export default function Calendar() {
  const [addDay, setAddDay] = useState<Date | null>(null);
  const [cursor, setCursor] = useState(() => {
    const n = new Date();
    return { year: n.getFullYear(), month: n.getMonth() };
  });

  const range = useMemo(() => {
    const from = new Date(cursor.year, cursor.month - 1, 1).toISOString();
    const to = new Date(cursor.year, cursor.month + 2, 0, 23, 59).toISOString();
    return { from, to };
  }, [cursor]);

  const q = useQuery({
    queryKey: ["calendar-interviews", range.from, range.to],
    queryFn: () => calendar.interviews(range.from, range.to),
  });

  const shift = (delta: number) =>
    setCursor((c) => {
      const m = c.month + delta;
      return { year: c.year + Math.floor(m / 12), month: ((m % 12) + 12) % 12 };
    });

  const label = new Date(cursor.year, cursor.month, 1).toLocaleDateString(
    undefined,
    { month: "long", year: "numeric" },
  );

  const header = (
    <div className="flex items-center gap-3 mb-3">
      <h1 className="text-lg font-semibold">Calendar</h1>
      <div className="ml-auto flex items-center gap-2">
        <IconButton onClick={() => shift(-1)} aria-label="Previous month">
          ‹
        </IconButton>
        <span className="text-sm w-36 text-center">{label}</span>
        <IconButton onClick={() => shift(1)} aria-label="Next month">
          ›
        </IconButton>
      </div>
    </div>
  );

  if (!q.data) {
    return (
      <div className="p-4 max-w-5xl mx-auto">
        {header}
        <div>{q.isError ? "Failed to load interviews." : "Loading…"}</div>
      </div>
    );
  }

  const events = q.data;

  return (
    <div className="p-4 max-w-5xl mx-auto">
      {header}
      <div className="hidden md:block">
        <MonthGrid year={cursor.year} month={cursor.month} events={events} onDayClick={setAddDay} />
      </div>
      <div className="md:hidden">
        <AgendaList events={events} />
      </div>
      {addDay && <AddInterviewDialog day={addDay} onClose={() => setAddDay(null)} />}
    </div>
  );
}
