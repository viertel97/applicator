"""One-shot LLM categorization for legacy `other` labels.

Used by the worker-startup ``tasks.categorize_existing_labels`` task.
Synchronous, batched, idempotent at the row level (only writes when
the LLM picks a real category and only touches `category = 'other'`
rows).
"""

import json
import logging
from typing import Iterable

from app.db.models import LabelCategory

logger = logging.getLogger(__name__)

BATCH_SIZE = 20

# `other` is intentionally excluded — the LLM must commit to a real
# category or leave the row to fall through.
_CATEGORY_CHOICES = [
    c.value for c in LabelCategory if c is not LabelCategory.other
]

SYSTEM = (
    "You categorize free-form job-posting labels into a fixed taxonomy. "
    "Return ONLY a JSON object mapping each input label name (exactly as "
    "given) to one category value from the schema. Do not invent "
    "categories. Pick the single best fit."
)


def _build_schema(names: list[str]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(names),
        "properties": {
            name: {"enum": _CATEGORY_CHOICES} for name in names
        },
    }


def _user_prompt(names: list[str]) -> str:
    listing = "\n".join(f"- {n}" for n in names)
    return (
        "Label names:\n"
        f"{listing}\n\n"
        "Categories: " + ", ".join(_CATEGORY_CHOICES) + "."
    )


def categorize_names(names: list[str], llm) -> dict[str, LabelCategory]:
    """Classify ``names`` in one LLM call. Returns name→category map.

    Names whose LLM answer is not a valid category are omitted from
    the map. JSON parse errors return an empty map.
    """
    if not names:
        return {}
    schema = _build_schema(names)
    raw = llm.complete(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": _user_prompt(names)},
        ],
        json_schema=schema,
        temperature=0.0,
    )
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("categorize: JSON decode error: %s", exc)
        return {}
    out: dict[str, LabelCategory] = {}
    for name, value in decoded.items():
        try:
            out[name] = LabelCategory(value)
        except ValueError:
            logger.warning("categorize: invalid category %r for %r", value, name)
    return out


def iter_batches(names: list[str], size: int = BATCH_SIZE) -> Iterable[list[str]]:
    for i in range(0, len(names), size):
        yield names[i : i + size]
