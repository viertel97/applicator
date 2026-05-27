from datetime import datetime, timezone

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.db.models import Application, ApplicationEvent, ApplicationEventKind


def _record_status_changes(session: Session, flush_context, instances) -> None:
    pending: list[ApplicationEvent] = []
    for obj in session.dirty:
        if not isinstance(obj, Application):
            continue
        hist = inspect(obj).attrs.status.history
        if not hist.has_changes():
            continue
        old = hist.deleted[0] if hist.deleted else None
        new = hist.added[0] if hist.added else obj.status
        if old == new:
            continue
        pending.append(ApplicationEvent(
            application_id=obj.id,
            kind=ApplicationEventKind.status_change,
            from_value=old.value if old is not None else None,
            to_value=new.value if new is not None else None,
            occurred_at=datetime.now(timezone.utc),
        ))
    for ev in pending:
        session.add(ev)


def register() -> None:
    if not event.contains(Session, "before_flush", _record_status_changes):
        event.listen(Session, "before_flush", _record_status_changes)
