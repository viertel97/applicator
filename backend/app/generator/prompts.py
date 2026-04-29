from app.extractor.schemas import ExtractedJobPosting

SYSTEM = (
    "You are a senior career coach. Write a tailored Anschreiben (cover letter) "
    "in Markdown. Use the candidate's CV and the default Anschreiben template as base. "
    "Match the candidate's strengths to the role's requirements. "
    "Write in the language given. Output only the Markdown of the letter, "
    "no commentary, no code fences."
)


def user_prompt(
    job: ExtractedJobPosting,
    cv_md: str,
    anschreiben_md: str,
    language: str,
) -> str:
    return (
        f"Target language: {language}\n\n"
        f"=== JOB POSTING ===\n"
        f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n"
        f"Description:\n{job.description}\nRequirements:\n{job.requirements}\n"
        f"Tech stack: {', '.join(job.tech_stack)}\n"
        f"Contact person: {job.contact_person}\n\n"
        f"=== CANDIDATE CV (Markdown) ===\n{cv_md}\n\n"
        f"=== DEFAULT ANSCHREIBEN TEMPLATE (Markdown) ===\n{anschreiben_md}\n\n"
        f"Now produce the tailored Anschreiben in Markdown, in {language}."
    )
