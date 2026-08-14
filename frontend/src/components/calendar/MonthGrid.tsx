import { monthMatrix, eventsForDay } from "../../lib/calendarBuckets";
import type { CalendarInterview } from "../../api/calendar";
import { InterviewChip } from "./InterviewChip";

export function MonthGrid({
  year,
  month,
  events,
}: {
  year: number;
  month: number;
  events: CalendarInterview[];
}) {
  const weeks = monthMatrix(year, month);
  const dows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return (
    <div className="grid grid-cols-7 gap-px bg-border rounded overflow-hidden">
      {dows.map((d) => (
        <div
          key={d}
          className="bg-surface px-2 py-1 text-xs font-semibold text-muted"
        >
          {d}
        </div>
      ))}
      {weeks.flat().map((day) => {
        const inMonth = day.getMonth() === month;
        const dayEvents = eventsForDay(events, day);
        return (
          <div
            key={day.toISOString()}
            className={`bg-bg min-h-[5rem] p-1 ${inMonth ? "" : "opacity-40"}`}
          >
            <div className="text-[11px] text-muted">{day.getDate()}</div>
            <div className="flex flex-col gap-0.5">
              {dayEvents.map((ev) => (
                <InterviewChip key={ev.id} ev={ev} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
