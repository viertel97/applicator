from app.extractor.schemas import ExtractedJobPosting


DEFAULT_TEMPLATE = (
    "Bestimme f\u00fcr eine Offene Fragen-Bewerbungsmail genau zwei Felder als JSON:\n"
    "- \"subject\": Betreff. "
    "Falls eine Referenznummer vorhanden ist: "
    "'Offene Fragen \u2013 [Stelle] (Ref. [Nr.])'. "
    "Sonst: 'Offene Fragen \u2013 [Stelle]'.\n"
    "- \"greeting\": Anrede ohne Komma. "
    "Beispiele: 'Sehr geehrte Frau M\u00fcller', "
    "'Sehr geehrter Herr Schmidt', "
    "'Sehr geehrte Damen und Herren'. "
    "Nur Nachname, kein Vorname. "
    "Bei Sprache 'en': 'Dear Ms Smith' / 'Dear Mr Jones' / 'Dear Sir or Madam'.\n\n"
    "Nur diese zwei Felder zur\u00fcckgeben. Kein Body, kein Text au\u00dferhalb des JSON."
)

def build_body(
    greeting: str,
    title: str,
    ref_number: str | None,
    questions: list[str],
    language: str,
) -> str:
    lang = (language or "de").lower()
    ref_part = f" (Ref. {ref_number})" if ref_number else ""
    q_block = "\n".join(questions)
    n = len(questions)
    if lang == "en":
        count = "one question" if n == 1 else "a couple of questions"
        return (
            f"{greeting},\n\n"
            f'I am very interested in your job posting for the position of "{title}{ref_part}". '
            f"Before submitting my application, I have {count}:\n\n"
            f"{q_block}\n\n"
            f"Thank you in advance for your reply.\n\n"
            f"Kind regards\n"
            f"Janik Viertel"
        )
    count = "eine kurze Frage" if n == 1 else "zwei kurze Fragen"
    return (
        f"{greeting},\n\n"
        f"ich interessiere mich sehr f\u00fcr Ihre Stellenausschreibung als "
        f"\u201e{title}{ref_part}\u201c. "
        f"Bevor ich meine Bewerbung einreiche, h\u00e4tte ich {count}:\n\n"
        f"{q_block}\n\n"
        f"Vielen Dank im Voraus f\u00fcr Ihre R\u00fcckmeldung und mit freundlichen Gr\u00fc\u00dfen\n"
        f"Janik Viertel"
    )


DEFAULT_USER_PROMPT_TEMPLATE = (
    "Zielsprache: {language}\n"
    "Stelle: {title}\n"
    "{ref_line}"
    "Ansprechpartner: {contact}\n\n"
    "Fragen, die in der Mail vorkommen MUESSEN (in dieser Reihenfolge):\n"
    "{questions}"
)

DEFAULT_HO_TOPIC_DE = (
    "Wie flexibel gestaltet sich der Homeoffice-Anteil, sofern Projektanforderungen und Termine zuverlässig erfüllt werden?"
)
DEFAULT_HO_TOPIC_EN = (
    "How many days of home office per week are possible, assuming customer "
    "projects and other requirements are met?"
)
DEFAULT_PT_TOPIC_DE = (
    "Wäre eine Beschäftigung in Teilzeit mit 80 % (z. B. Montag bis Donnerstag) grundsätzlich denkbar?"
)
DEFAULT_PT_TOPIC_EN = (
    "Would an 80% position (Monday to Thursday) be possible in principle?"
)


def _topic_lines(
    language: str,
    ask_ho: bool,
    ask_pt: bool,
    ho_de: str | None = None,
    ho_en: str | None = None,
    pt_de: str | None = None,
    pt_en: str | None = None,
) -> list[str]:
    lang = (language or "de").lower()
    out: list[str] = []
    if ask_ho:
        if lang == "en":
            out.append(ho_en or DEFAULT_HO_TOPIC_EN)
        else:
            out.append(ho_de or DEFAULT_HO_TOPIC_DE)
    if ask_pt:
        if lang == "en":
            out.append(pt_en or DEFAULT_PT_TOPIC_EN)
        else:
            out.append(pt_de or DEFAULT_PT_TOPIC_DE)
    return out


def user_prompt(
    *,
    job: ExtractedJobPosting,
    language: str,
    ask_home_office: bool,
    ask_part_time: bool,
    template: str | None = None,
    ho_de: str | None = None,
    ho_en: str | None = None,
    pt_de: str | None = None,
    pt_en: str | None = None,
) -> str:
    topics = _topic_lines(language, ask_home_office, ask_part_time, ho_de, ho_en, pt_de, pt_en)
    bullet_block = "\n".join(f"- {t}" for t in topics)
    contact_name = job.contact.name if job.contact and job.contact.name else "unbekannt"
    ref_line = f"Referenznummer: {job.reference_number}\n" if job.reference_number else ""

    tpl = template or DEFAULT_USER_PROMPT_TEMPLATE
    return tpl.format(
        language=language,
        title=job.title or "unbekannt",
        company=job.company or "unbekannt",
        contact=contact_name,
        ref_line=ref_line,
        reference_number=job.reference_number or "",
        questions=bullet_block,
    )
