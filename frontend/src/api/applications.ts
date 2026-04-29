import { api } from "./client";

export type AppStatus = "draft" | "applied" | "offer" | "rejected" | "accepted" | "withdrawn";
export type JobState = "pending" | "crawling" | "extracting" | "generating" | "ready" | "failed";

export type JobPosting = {
  title: string | null;
  company: string | null;
  location: string | null;
  description: string | null;
  requirements: string | null;
  contact_person: string | null;
  application_email: string | null;
  deadline: string | null;
  salary: string | null;
  tech_stack: string[] | null;
  seniority: string | null;
  work_mode: string | null;
  benefits: string[] | null;
  language: string | null;
};

export type Application = {
  id: string;
  url: string;
  status: AppStatus;
  job_state: JobState;
  job_error: string | null;
  language: string | null;
  generated_md: string | null;
  has_docx: boolean;
  job_posting: JobPosting | null;
};

export const applications = {
  list: () => api<Application[]>("/api/applications"),
  get: (id: string) => api<Application>(`/api/applications/${id}`),
  create: (url: string) =>
    api<Application>("/api/applications", { method: "POST", body: JSON.stringify({ url }) }),
  setStatus: (id: string, status: AppStatus) =>
    api<Application>(`/api/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  retry: (id: string) =>
    api<Application>(`/api/applications/${id}/retry`, { method: "POST" }),
  docxUrl: (id: string) => `/api/applications/${id}/docx`,
};
