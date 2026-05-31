from datetime import datetime

from pydantic import BaseModel, Field


class ParsedMessage(BaseModel):
    sender_name: str | None = None
    sender_email: str | None = None
    recipients: list[str] = Field(default_factory=list)
    occurred_at: datetime | None = None
    subject: str | None = None
    body: str = ""


class ParsedThread(BaseModel):
    messages: list[ParsedMessage] = Field(default_factory=list)
    used_llm: bool = False
