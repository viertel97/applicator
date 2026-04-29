from pydantic import BaseModel, Field


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
