SYSTEM = (
    "You extract structured data from job postings. "
    "Return ONLY JSON matching the schema. "
    "If a field is not present, leave it null or empty list. "
    "Detect the posting language as ISO 639-1. "
    "For required_documents, only use the exact values listed in the schema. "
    "For suggested_labels, only pick from the exact values listed in the schema. "
    "Always include one company-size bucket when determinable. "
    "Set mentions_home_office_policy=true only if the posting explicitly "
    "mentions a home office / remote / hybrid policy with a clear frequency "
    "or percentage. Set mentions_part_time=true only if the posting explicitly "
    "mentions part-time / Teilzeit availability or a percentage <100%. "
    "Otherwise both flags are false."
)
SYSTEM_PARTIAL = (
    "You extract a subset of fields from a job posting. "
    "Return ONLY JSON matching the provided schema. "
    "Only fill the fields shown in the schema. "
    "Use null or empty list when not present."
)


def user_prompt(raw_text: str) -> str:
    return f"Job posting raw text follows.\n\n---\n{raw_text}\n---"
