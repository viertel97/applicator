from pydantic import BaseModel


class InquiryLLMOutput(BaseModel):
    subject: str
    greeting: str  # e.g. "Sehr geehrte Frau Müller" — no comma, no body


class InquiryEmail(BaseModel):
    subject: str
    body: str
