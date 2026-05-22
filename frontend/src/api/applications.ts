import { api } from "./client";

export type AppStatus = "draft" | "applied" | "offer" | "rejected" | "accepted" | "withdrawn";
export type JobState =
  | "pending"
  | "crawling"
  | "extracting"
  | "extracted"
  | "generating"
  | "ready"
  | "failed";
export type FailedStage = "crawl" | "extract" | "generate";

export type LabelCategory =
  | "role" | "tech" | "domain" | "seniority"
  | "work_mode" | "location" | "company_size"
  | "language" | "company" | "other";

export type Label = {
  id: string;
  name: string;
  color: string;
  is_auto: boolean;
  category: LabelCategory;
};

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
  required_documents: string[] | null;
};

export type Application = {
  id: string;
  display_id: number;
  url: string;
  status: AppStatus;
  job_state: JobState;
  job_error: string | null;
  failed_stage: FailedStage | null;
  language: string | null;
  generated_md: string | null;
  has_docx: boolean;
  cv_variant_id: string | null;
  anschreiben_variant_id: string | null;
  job_posting_dirty: boolean;
  posting_online: boolean | null;
  labels: Label[];
  job_posting: JobPosting | null;
};

export type CreateApplicationBody = {
  url: string;
  cv_variant_id?: string | null;
  anschreiben_variant_id?: string | null;
};

export type VariantsPatchBody = {
  cv_variant_id?: string;
  anschreiben_variant_id?: string;
  clear_cv?: boolean;
  clear_anschreiben?: boolean;
};

export const applications = {
  list: (labelIds?: string[]) => {
    const params = labelIds?.length
      ? "?" + labelIds.map((id) => `label_ids=${id}`).join("&")
      : "";
    return api<Application[]>(`/api/applications${params}`);
  },
  get: (id: string) => api<Application>(`/api/applications/${id}`),
  create: (body: CreateApplicationBody) =>
    api<Application>("/api/applications", { method: "POST", body: JSON.stringify(body) }),
  setStatus: (id: string, status: AppStatus) =>
    api<Application>(`/api/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  patchJobPosting: (id: string, fields: Partial<JobPosting>) =>
    api<Application>(`/api/applications/${id}/job-posting`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    }),
  patchVariants: (id: string, body: VariantsPatchBody) =>
    api<Application>(`/api/applications/${id}/variants`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  generate: (id: string) =>
    api<Application>(`/api/applications/${id}/generate`, { method: "POST" }),
  retry: (id: string) =>
    api<Application>(`/api/applications/${id}/retry`, { method: "POST" }),
  docxUrl: (id: string) => `/api/applications/${id}/docx`,
};
