from pydantic import BaseModel


class InquiryEmail(BaseModel):
    subject: str
    body: str
