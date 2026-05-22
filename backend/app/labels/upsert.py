"""Single write path for category-tagged labels.

Called by the extractor pipeline, the backfill processor, and any
future code that needs to attach labels to an Application.
"""

from typing import Mapping

from sqlalchemy.orm import Session

from app.db.models import Application, Label, LabelCategory
from app.extractor.schemas import LabelSuggestions

_AUTO_LABEL_COLOR = "#6366f1"


def _get_or_create_label(
    db: Session, name: str, category: LabelCategory
) -> Label:
    label = db.query(Label).filter_by(name=name).first()
    if label is None:
        label = Label(name=name, color=_AUTO_LABEL_COLOR, is_auto=True, category=category)
        db.add(label)
        db.flush()
    return label


def upsert_and_assign_labels(
    db: Session,
    app: Application,
    suggestions: LabelSuggestions | Mapping[str, list[str]],
) -> None:
    """Create any missing labels, then attach them to ``app``.

    Existing labels keep their category — a later extraction that
    classifies the same name differently does **not** overwrite the
    first classification.

    Accepts either a ``LabelSuggestions`` instance (pipeline path) or a
    plain dict keyed by category name (backfill receives the raw LLM
    output as a dict via ``extract_fields``).
    """
    if isinstance(suggestions, LabelSuggestions):
        items = suggestions.model_dump()
    else:
        items = dict(suggestions or {})

    for category_name, names in items.items():
        if not names:
            continue
        try:
            category = LabelCategory(category_name)
        except ValueError:
            # Unknown category from a misbehaving LLM payload — skip.
            continue
        for name in names:
            if not name:
                continue
            label = _get_or_create_label(db, name, category)
            if label not in app.labels:
                app.labels.append(label)
