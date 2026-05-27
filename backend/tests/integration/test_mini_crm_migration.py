"""Smoke-tests the migration's backfill helpers via direct execution.

We can't easily run alembic against the testcontainer mid-test; instead this
test asserts the helper logic (SYSTEM_REASONS shape, slug list completeness)
that the migration relies on. The Postgres-level schema is exercised by the
normal db_session fixture via Base.metadata.create_all.
"""


def _load_migration_module():
    """Load the migration module directly from its file path.

    `alembic/versions/` is not a Python package (no __init__.py), so we use
    importlib.util to import it from its file path.
    """
    import importlib.util
    from pathlib import Path

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "c4d5e6f7a8b9_mini_crm.py"
    )
    spec = importlib.util.spec_from_file_location(
        "c4d5e6f7a8b9_mini_crm", str(migration_path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_system_reasons_list_has_ten_unique_slugs():
    # The migration module exposes SYSTEM_REASONS at module top.
    mod = _load_migration_module()
    slugs = [s for s, _, _ in mod.SYSTEM_REASONS]
    assert len(slugs) == 10
    assert len(set(slugs)) == 10
    expected = {
        "no_reply", "rejected", "withdrew_self", "location", "salary",
        "tech_mismatch", "seniority", "posting_offline", "duplicate", "other",
    }
    assert set(slugs) == expected


def test_application_event_created_row_per_app_smoke(db_session, auth_user):
    """Smoke: with the models from Task 1 + the migration code's intended
    INSERT shape, we can write one 'created' event per app and read it back."""
    from app.db.models import (
        Application,
        ApplicationEvent,
        ApplicationEventKind,
    )

    _, u = auth_user
    apps = []
    for i in range(3):
        a = Application(user_id=u.id, url=f"https://x.test/m{i}", url_hash=f"hm{i}")
        db_session.add(a)
        apps.append(a)
    db_session.commit()
    # Emulate the migration's bulk insert of created events
    for a in apps:
        db_session.add(
            ApplicationEvent(
                application_id=a.id,
                kind=ApplicationEventKind.created,
                occurred_at=a.created_at,
            )
        )
    db_session.commit()
    cnt = (
        db_session.query(ApplicationEvent)
        .filter_by(kind=ApplicationEventKind.created)
        .count()
    )
    assert cnt == 3
