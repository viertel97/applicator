from app.extractor.schemas import ExtractedJobPosting
from app.generator.prompts import SYSTEM, user_prompt
from app.llm.base import LLMClient


def generate(
    job: ExtractedJobPosting,
    cv_md: str,
    anschreiben_md: str,
    language: str,
    llm: LLMClient,
) -> str:
    return llm.complete(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt(job, cv_md, anschreiben_md, language)},
        ],
        temperature=0.3,
    ).strip()
