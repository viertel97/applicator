import { api } from "./client";

export type InquiryPrompt = {
  source_md: string;
  user_prompt_md: string | null;
  question_home_office_de: string | null;
  question_home_office_en: string | null;
  question_part_time_de: string | null;
  question_part_time_en: string | null;
  body_template_de: string | null;
  body_template_en: string | null;
};

export const inquiryPrompt = {
  get: () => api<InquiryPrompt>("/api/settings/inquiry-prompt"),
  put: (body: InquiryPrompt) =>
    api<InquiryPrompt>("/api/settings/inquiry-prompt", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};
