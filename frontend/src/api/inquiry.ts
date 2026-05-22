import { api } from "./client";

export type InquiryPrompt = { source_md: string };

export const inquiryPrompt = {
  get: () => api<InquiryPrompt>("/api/settings/inquiry-prompt"),
  put: (source_md: string) =>
    api<InquiryPrompt>("/api/settings/inquiry-prompt", {
      method: "PUT",
      body: JSON.stringify({ source_md }),
    }),
};
