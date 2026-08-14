import { useQuery } from "@tanstack/react-query";
import { calendar } from "../api/calendar";

export function useReviewCount(): number {
  const q = useQuery({
    queryKey: ["calendar-review-count"],
    queryFn: () => calendar.reviewCount(),
  });
  return q.data?.count ?? 0;
}
