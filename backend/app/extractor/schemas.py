from pydantic import BaseModel, Field

DOC_TYPES: tuple[str, ...] = ("cv", "cover_letter", "portfolio", "references", "certificates", "other")
_DOC_VOCAB = ", ".join(DOC_TYPES)


class ContactInfo(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None


class LabelSuggestions(BaseModel):
    role: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)
    domain: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    work_mode: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    company_size: list[str] = Field(
        default_factory=list,
        description="Exactly one of Startup, KMU, Mittelstand, Konzern when determinable.",
    )
    language: list[str] = Field(default_factory=list)
    company: list[str] = Field(default_factory=list)


class ExtractedJobPosting(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    requirements: str | None = None
    contact: ContactInfo | None = None
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
    reference_number: str | None = Field(
        default=None,
        description=(
            "Job reference / Referenznummer as printed in the posting "
            "(e.g. 'Ref. 12345', 'Kennziffer AB-2025-042'). Null if absent."
        ),
    )
    suggested_labels: LabelSuggestions = Field(default_factory=LabelSuggestions)
    mentions_home_office_policy: bool = Field(
        default=False,
        description=(
            "True iff the posting explicitly states a home office / remote / "
            "hybrid policy with frequency or percentage (e.g. 'Homeoffice "
            "möglich', '2 Tage pro Woche remote', 'fully remote', "
            "'hybrid 60/40'). False if home office is not mentioned at all "
            "or only vaguely implied."
        ),
    )
    mentions_part_time: bool = Field(
        default=False,
        description=(
            "True iff the posting explicitly mentions part-time availability "
            "(e.g. 'Teilzeit möglich', '80%', 'part-time'). False if only "
            "Vollzeit / full-time is mentioned or nothing is said about it."
        ),
    )
