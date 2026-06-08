from app.inquiry.preview import build_preview


def test_preview_renders_both_languages_with_sample_greeting():
    out = build_preview(source_md="SYS")
    assert set(out) == {"de", "en"}
    assert out["de"]["system_prompt"] == "SYS"
    assert out["de"]["greeting"] == "Sehr geehrte Frau Müller"
    assert out["en"]["greeting"] == "Dear Ms Müller"
    # canned subject + greeting land in stage 2 / stage 3
    assert out["de"]["subject"]
    assert out["de"]["greeting"] in out["de"]["email"]


def test_preview_questions_list_is_populated_and_present_in_email():
    de = build_preview(source_md="SYS")["de"]
    assert isinstance(de["questions"], list) and len(de["questions"]) == 2
    for q in de["questions"]:
        assert q in de["email"]
        assert q in de["user_prompt"]


def test_preview_custom_question_text_flows_through_de():
    de = build_preview(source_md="SYS", question_home_office_de="WUNSCH_HO_DE?")["de"]
    assert "WUNSCH_HO_DE?" in de["user_prompt"]
    assert "WUNSCH_HO_DE?" in de["email"]
    assert "WUNSCH_HO_DE?" in de["questions"]


def test_preview_custom_body_template_de_is_used():
    de = build_preview(source_md="SYS", body_template_de="DE::{greeting}::{questions}")["de"]
    assert de["email"].startswith("DE::Sehr geehrte Frau Müller::")


def test_preview_default_de_topics_use_backend_defaults():
    de = build_preview(source_md="SYS")["de"]
    assert "Homeoffice" in de["email"]  # DEFAULT_HO_TOPIC_DE wording
    assert "80" in de["email"]          # DEFAULT_PT_TOPIC_DE wording
