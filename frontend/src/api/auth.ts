import { api } from "./client";

export type Me = { id: string; email: string; display_name: string };

export const auth = {
  me: () => api<Me>("/api/auth/me"),
  logout: () => api<{ ok: true }>("/api/auth/logout", { method: "POST" }),
  loginUrl: () => "/api/auth/login",
};
