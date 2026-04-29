import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { auth } from "../api/auth";
import type { Me } from "../api/auth";

export function useAuth() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await auth.me();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}
