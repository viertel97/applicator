import { api } from "./client";

export type ChatMsg = { id: string; role: "user" | "assistant" | "system"; content: string };

export const chat = {
  history: (aid: string) => api<ChatMsg[]>(`/api/applications/${aid}/chat`),
  refine: (aid: string, message: string) =>
    api<{ assistant_message: string; generated_md: string }>(
      `/api/applications/${aid}/chat`,
      { method: "POST", body: JSON.stringify({ message }) },
    ),
};
