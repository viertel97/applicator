from pydantic import BaseModel, Field

_LABEL_CANDIDATES = (
    "Startup, Konzern, Remote, Hybrid, Finance, Tech, "
    "Agency, Consulting, NGO, Public Sector"
)
_DOC_VOCAB = "cv, cover_letter, portfolio, references, certificates, other"


class ExtractedJobPosting(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    requirements: str | None = None
    contact_person: str | None = None
    application_email: str | None = None
    deadline: str | None = None
    salary: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    seniority: str | None = None
    work_mode: str | None = None  # remote | hybrid | onsite
    benefits: list[str] = Field(default_factory=list)
    language: str = Field(description="ISO 639-1 of the posting body, e.g. 'de' or 'en'")
    required_documents: list[str] = Field(
        default_factory=list,
        description=(
            f"Documents required to apply. Only use values from: {_DOC_VOCAB}"
        ),
    )
    suggested_labels: list[str] = Field(
        default_factory=list,
        description=(
            f"Labels from this set that apply to the company/role: {_LABEL_CANDIDATES}. "
            "Return only values from this set."
        ),
    )
