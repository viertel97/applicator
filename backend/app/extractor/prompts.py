SYSTEM = (
    "You extract structured data from job postings. "
    "Return ONLY JSON matching the schema. "
    "If a field is not present, leave it null or empty list. "
    "Detect the posting language as ISO 639-1. "
    "For required_documents, only use the exact values listed in the schema. "
    "For suggested_labels, only pick from the exact values listed in the schema. "
    "Always include one company-size bucket when determinable. "
    "For 'contact', fill the sub-fields (name, role, email, phone) from any "
    "Ansprechpartner block, recruiter signature, sidebar contact card, mailto: "
    "or tel: link. Leave 'contact' null only when no identifiable contact "
    "info appears."
)
SYSTEM_PARTIAL = (
    "You extract a subset of fields from a job posting. "
    "Return ONLY JSON matching the provided schema. "
    "Only fill the fields shown in the schema. "
    "Use null or empty list when not present."
)


def user_prompt(raw_text: str) -> str:
    return f"Job posting raw text follows.\n\n---\n{raw_text}\n---"
