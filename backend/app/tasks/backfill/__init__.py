"""On-startup backfill: fills empty JobPosting fields and auto-labels via Groq."""

from .pacing import _adaptive_sleep
from .processor import (
    ELIGIBLE_FIELDS,
    SUGGESTED_LABELS,
    pick_missing,
    process_row,
)
from .task import backfill_missing_task

__all__ = [
    "ELIGIBLE_FIELDS",
    "SUGGESTED_LABELS",
    "_adaptive_sleep",
    "backfill_missing_task",
    "pick_missing",
    "process_row",
]
