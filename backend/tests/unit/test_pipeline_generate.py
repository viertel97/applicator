import uuid
from pathlib import Path
from unittest.mock import MagicMock

from app.db.models import (
    AnschreibenVariant,
    Application,
    CVVariant,
    JobPosting,
    JobState,
)
from app.pipeline.generate import run_generate
from tests.fakes.llm import FakeLLM


def test_run_generate_writes_md_and_docx(tmp_path):
    settings = MagicMock(data_dir=str(tmp_path))
    db = MagicMock()
    app = Application(url="u", url_hash="h" * 64)
    app.id = uuid.uuid4()
    app.display_id = 42
    app.user_id = uuid.uuid4()
    app.job_state = JobState.extracted
    cv_id, an_id = uuid.uuid4(), uuid.uuid4()
    app.cv_variant_id = cv_id
    app.anschreiben_variant_id = an_id
    app.job_posting_dirty = True
    app.job_posting = JobPosting(
        application_id=app.id,
        raw_text="x",
        title="Dev",
        company="Acme Corp",
        language="en",
    )
    cv = CVVariant(id=cv_id, name="cv", source_md="cv md")
    an = AnschreibenVariant(id=an_id, name="an", source_md="an md")

    def fake_get(model, key):
        if model is CVVariant:
            return cv
        if model is AnschreibenVariant:
            return an
        return None

    db.get.side_effect = fake_get
    llm = FakeLLM(handler=lambda m, s: "# Dear hiring team")

    run_generate(db, app, llm, settings)

    assert app.job_state == JobState.ready
    assert app.generated_md.startswith("# Dear")
    assert Path(app.generated_docx_path).exists()
    assert "0042_acme-corp_dev" in app.generated_docx_path
    assert app.job_posting_dirty is False
    assert app.failed_stage is None
