from app.extractor.schemas import ExtractedJobPosting


DEFAULT_TEMPLATE = (
    "Du hilfst dem Bewerber, eine kurze, höfliche Vorab-Mail an den "
    "Ansprechpartner einer Stellenausschreibung zu schreiben. Ziel: zwei "
    "offene Punkte vor der eigentlichen Bewerbung klären.\n\n"
    "Regeln:\n"
    "- Maximal acht Sätze.\n"
    "- Nur die im Nutzer-Prompt explizit genannten Fragen stellen, keine "
    "  weiteren Themen.\n"
    "- Höflicher, professioneller Ton; keine Selbstvermarktung, kein CV-Pitch.\n"
    "- Am Ende fragen, ob eine Bewerbung unter diesen Bedingungen willkommen "
    "  ist.\n"
    "- Antwort als JSON {\"subject\": \"...\", \"body\": \"...\"}. "
    "Absätze im body mit \\n\\n trennen, keine HTML-Tags. "
    "Falls eine Referenznummer angegeben ist, diese im Subject verwenden "
    "(z.B. 'Vorab-Anfrage – Stelle XY (Ref. 12345)').\n"
    "- Sprache exakt an die im Nutzer-Prompt angegebene Zielsprache anpassen "
    "  (z.B. 'de' oder 'en')."
)

_HO_TOPIC_DE = (
    "Wie viele Tage Home Office pro Woche sind möglich, unter der "
    "Voraussetzung, dass Kundenprojekte und sonstige Anforderungen erfüllt "
    "sind?"
)
_HO_TOPIC_EN = (
    "How many days of home office per week are possible, assuming customer "
    "projects and other requirements are met?"
)
_PT_TOPIC_DE = (
    "Wäre eine 80%-Stelle (Montag bis Donnerstag) grundsätzlich denkbar?"
)
_PT_TOPIC_EN = (
    "Would an 80% position (Monday to Thursday) be possible in principle?"
)


def _topic_lines(language: str, ask_ho: bool, ask_pt: bool) -> list[str]:
    lang = (language or "de").lower()
    out: list[str] = []
    if ask_ho:
        out.append(_HO_TOPIC_EN if lang == "en" else _HO_TOPIC_DE)
    if ask_pt:
        out.append(_PT_TOPIC_EN if lang == "en" else _PT_TOPIC_DE)
    return out


def user_prompt(
    *,
    job: ExtractedJobPosting,
    language: str,
    ask_home_office: bool,
    ask_part_time: bool,
) -> str:
    topics = _topic_lines(language, ask_home_office, ask_part_time)
    bullet_block = "\n".join(f"- {t}" for t in topics)
    contact_name = job.contact.name if job.contact and job.contact.name else "unbekannt"
    ref_line = (
        f"Referenznummer: {job.reference_number}\n" if job.reference_number else ""
    )
    return (
        f"Zielsprache: {language}\n"
        f"Stelle: {job.title or 'unbekannt'} bei {job.company or 'unbekannt'}\n"
        f"{ref_line}"
        f"Ansprechpartner: {contact_name}\n\n"
        f"Fragen, die in der Mail vorkommen MUESSEN (in dieser Reihenfolge):\n"
        f"{bullet_block}"
    )
