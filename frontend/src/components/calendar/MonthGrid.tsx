import { monthMatrix, eventsForDay, dayKey } from "../../lib/calendarBuckets";
import type { CalendarInterview } from "../../api/calendar";
import { InterviewChip } from "./InterviewChip";

export function MonthGrid({
  year,
  month,
  events,
  onDayClick,
}: {
  year: number;
  month: number;
  events: CalendarInterview[];
  onDayClick?: (day: Date) => void;
}) {
  const weeks = monthMatrix(year, month);
  const dows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const todayKey = dayKey(new Date());
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
        const isToday = dayKey(day) === todayKey;
        const clickProps = onDayClick
          ? {
              role: "button" as const,
              tabIndex: 0,
              "aria-label": day.toLocaleDateString(undefined, {
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric",
              }),
              onClick: () => onDayClick(day),
              onKeyDown: (e: React.KeyboardEvent) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onDayClick(day);
                }
              },
            }
          : {};
        return (
          <div
            key={dayKey(day)}
            className={[
              "bg-bg min-h-[5rem] p-1",
              inMonth ? "" : "opacity-40",
              isToday ? "ring-1 ring-accent" : "",
              onDayClick ? "cursor-pointer" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            {...clickProps}
          >
            {isToday ? (
              <span className="inline-flex items-center justify-center min-w-[1.25rem] h-[1.25rem] rounded-full text-[11px] bg-accent text-accentFg">
                {day.getDate()}
              </span>
            ) : (
              <div className="text-[11px] text-muted">{day.getDate()}</div>
            )}
            <div
              className="flex flex-col gap-0.5"
              onClick={(e) => e.stopPropagation()}
            >
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
