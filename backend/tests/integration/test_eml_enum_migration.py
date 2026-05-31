import importlib.util
from pathlib import Path

from app.db.models import (
    Application,
    Interaction,
    InteractionChannel,
    InteractionCreatedFrom,
    InteractionDirection,
)


def _load_migration():
    p = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "e1f2a3b4c5d6_interaction_created_from_eml_import.py"
    )
    spec = importlib.util.spec_from_file_location("eml_enum_mig", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_enum_member_exists():
    assert InteractionCreatedFrom.eml_import.value == "eml_import"


def test_migration_chains_from_head():
    mod = _load_migration()
    assert mod.revision == "e1f2a3b4c5d6"
    assert mod.down_revision == "d5e6f7a8b9c0"


def test_can_persist_interaction_with_eml_import(db_session, auth_user):
    _, u = auth_user
    a = Application(user_id=u.id, url="https://x.test/e", url_hash="he")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    it = Interaction(
        application_id=a.id,
        direction=InteractionDirection.in_,
        channel=InteractionChannel.mail,
        created_from=InteractionCreatedFrom.eml_import,
    )
    db_session.add(it)
    db_session.commit()
    db_session.refresh(it)
    assert it.created_from == InteractionCreatedFrom.eml_import
