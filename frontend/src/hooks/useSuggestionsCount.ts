import { useQuery } from "@tanstack/react-query";
import { applications } from "../api/applications";
import { calendar } from "../api/calendar";

// Open-suggestion count for the nav badge. Shares the ["suggestions"] and
// ["calendar-suggestions"] caches with the Suggestions page so actions there
// update the badge live.
export function useSuggestionsCount(): number {
  const offline = useQuery({
    queryKey: ["suggestions"],
    queryFn: () => applications.getSuggestions(),
  });
  const cal = useQuery({
    queryKey: ["calendar-suggestions"],
    queryFn: () => calendar.suggestions(),
  });
  return (offline.data?.length ?? 0) + (cal.data?.length ?? 0);
}
