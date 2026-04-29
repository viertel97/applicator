import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep, settings_dep
from app.config import Settings
from app.db.models import Application, ChatMessage, ChatRole, User
from app.llm.base import LLMClient
from app.llm.groq import GroqClient
from app.renderer.docx import to_docx

router = APIRouter(prefix="/api/applications", tags=["chat"])

SYSTEM_REFINE = (
    "You are a writing assistant. The user already has a generated Anschreiben in Markdown. "
    "When the user asks for changes, return TWO things in JSON: "
    '{"assistant_message": str, "updated_md": str}. '
    "updated_md must be the full new Anschreiben in Markdown."
)

REFINE_SCHEMA = {
    "type": "object",
    "properties": {
        "assistant_message": {"type": "string"},
        "updated_md": {"type": "string"},
    },
    "required": ["assistant_message", "updated_md"],
}


class ChatIn(BaseModel):
    message: str


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: ChatRole
    content: str

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    assistant_message: str
    generated_md: str


def _llm(settings: Settings) -> LLMClient:
    return GroqClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )


@router.get("/{aid}/chat", response_model=list[ChatMessageOut])
def history(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = db.get(Application, aid)
    if not app_row or app_row.user_id != user.id:
        raise HTTPException(404, "not found")
    return (
        db.query(ChatMessage)
        .filter_by(application_id=aid)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )


@router.post("/{aid}/chat", response_model=ChatResponse)
def refine(
    aid: uuid.UUID,
    body: ChatIn,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    settings: Annotated[Settings, Depends(settings_dep)],
):
    app_row = db.get(Application, aid)
    if not app_row or app_row.user_id != user.id:
        raise HTTPException(404, "not found")
    if not app_row.generated_md:
        raise HTTPException(400, "no Anschreiben yet")
    client = _llm(settings)
    history_rows = (
        db.query(ChatMessage)
        .filter_by(application_id=aid)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_REFINE},
        {"role": "system", "content": f"CURRENT_MD:\n{app_row.generated_md}"},
    ]
    for h in history_rows:
        messages.append({"role": h.role.value, "content": h.content})
    messages.append({"role": "user", "content": body.message})

    raw = client.complete(messages, json_schema=REFINE_SCHEMA, temperature=0.4)
    parsed = json.loads(raw)
    assistant_msg = parsed["assistant_message"]
    new_md = parsed["updated_md"]

    db.add(ChatMessage(application_id=aid, role=ChatRole.user, content=body.message))
    db.add(ChatMessage(application_id=aid, role=ChatRole.assistant, content=assistant_msg))
    app_row.generated_md = new_md
    if app_row.generated_docx_path:
        to_docx(new_md, app_row.generated_docx_path)
    db.commit()
    return ChatResponse(assistant_message=assistant_msg, generated_md=new_md)
