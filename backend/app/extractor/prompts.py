SYSTEM = (
    "You extract structured data from job postings. "
    "Return ONLY JSON matching the schema. "
    "If a field is not present, leave it null or empty list. "
    "Detect the posting language as ISO 639-1. "
    "For required_documents, only use the exact values listed in the schema. "
    "For suggested_labels, place each label under the matching category "
    "field: role, tech, domain, seniority, work_mode, location, "
    "company_size, language, company. Leave a category empty if nothing "
    "fits. Pick exactly one company_size bucket "
    "(Startup/KMU/Mittelstand/Konzern) when determinable from explicit "
    "headcount or general knowledge of the named company."
)


def user_prompt(raw_text: str) -> str:
    return f"Job posting raw text follows.\n\n---\n{raw_text}\n---"
