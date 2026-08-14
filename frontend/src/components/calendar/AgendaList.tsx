import { groupByDay } from "../../lib/calendarBuckets";
import type { CalendarInterview } from "../../api/calendar";
import { InterviewChip } from "./InterviewChip";

export function AgendaList({ events }: { events: CalendarInterview[] }) {
  const groups = groupByDay(events);
  if (groups.length === 0)
    return <p className="text-muted text-sm p-4">No upcoming interviews.</p>;
  return (
    <div className="flex flex-col gap-4">
      {groups.map((g) => (
        <div key={g.key}>
          <h3 className="text-sm font-semibold mb-1">
            {g.date.toLocaleDateString(undefined, {
              weekday: "short",
              month: "short",
              day: "numeric",
            })}
          </h3>
          <div className="flex flex-col gap-1">
            {g.items.map((ev) => (
              <InterviewChip key={ev.id} ev={ev} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
