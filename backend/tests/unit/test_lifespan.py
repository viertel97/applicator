from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def test_startup_enqueues_backfill_and_categorize():
    with (
        patch("app.main.backfill_missing_task") as backfill,
        patch("app.main.categorize_existing_labels_task") as categorize,
    ):
        app = create_app()
        with TestClient(app):
            pass
        backfill.apply_async.assert_called_once()
        categorize.apply_async.assert_called_once()
