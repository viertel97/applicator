from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import urlparse


@dataclass
class Candidate:
    application_id: str
    company: str | None
    url: str


def _domain(email_or_url: str) -> str:
    if "@" in email_or_url:
        return email_or_url.rsplit("@", 1)[-1].lower()
    return urlparse(email_or_url).netloc.lower().removeprefix("www.")


def _root(domain: str) -> str:
    parts = domain.split(".")
    return parts[-2] if len(parts) >= 2 else domain


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def _score(sender: str, text: str, cand: Candidate) -> float:
    score = 0.0
    sender_root = _root(_domain(sender))
    cand_root = _root(_domain(cand.url))
    if sender_root and sender_root == cand_root:
        score += 1.0
    if cand.company:
        company_norm = _norm(cand.company)
        if company_norm and company_norm in _norm(text):
            score += 0.8
        if sender_root and sender_root in company_norm:
            score += 0.5
        score += 0.3 * SequenceMatcher(None, company_norm, _norm(text)).ratio()
    return score


def match_application(
    *, sender: str, subject: str, body: str, candidates: list[Candidate]
) -> tuple[str | None, float]:
    if not candidates:
        return None, 0.0
    text = f"{subject} {body}"
    scored = [(c, _score(sender, text, c)) for c in candidates]
    best, best_score = max(scored, key=lambda x: x[1])
    return best.application_id, best_score
