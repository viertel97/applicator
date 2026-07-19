import { useQuery } from "@tanstack/react-query";
import { applications } from "../api/applications";

// Open-suggestion count for the nav badge. Shares the ["suggestions"] cache
// with the Suggestions page so dismiss/discard there updates the badge.
export function useSuggestionsCount(): number {
  const q = useQuery({
    queryKey: ["suggestions"],
    queryFn: () => applications.getSuggestions(),
  });
  return q.data?.length ?? 0;
}
