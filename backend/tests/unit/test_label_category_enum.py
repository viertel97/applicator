from app.db.models import LabelCategory


def test_label_category_members_exact():
    expected = [
        "role",
        "tech",
        "domain",
        "seniority",
        "work_mode",
        "location",
        "company_size",
        "language",
        "company",
        "other",
    ]
    assert [m.value for m in LabelCategory] == expected


def test_label_category_string_backed():
    assert LabelCategory.tech == "tech"
    assert isinstance(LabelCategory.tech, str)
