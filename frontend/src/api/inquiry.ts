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

export type InquiryPreviewLang = {
  system_prompt: string;
  user_prompt: string;
  subject: string;
  greeting: string;
  questions: string[];
  email: string;
};

export type InquiryPreviewOut = {
  de: InquiryPreviewLang;
  en: InquiryPreviewLang;
};

export const inquiryPrompt = {
  get: () => api<InquiryPrompt>("/api/settings/inquiry-prompt"),
  put: (body: InquiryPrompt) =>
    api<InquiryPrompt>("/api/settings/inquiry-prompt", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  preview: (body: InquiryPrompt) =>
    api<InquiryPreviewOut>("/api/settings/inquiry-prompt/preview", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
