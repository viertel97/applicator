export const ALL_DOCS = ["cv", "cover_letter", "portfolio", "references", "certificates", "other"] as const;
export type RequiredDoc = typeof ALL_DOCS[number];
export const DOC_LABEL: Record<RequiredDoc, string> = {
  cv: "CV",
  cover_letter: "Cover letter",
  portfolio: "Portfolio",
  references: "References",
  certificates: "Certificates",
  other: "Other",
};
