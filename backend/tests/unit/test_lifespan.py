from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def test_startup_enqueues_backfill():
    with patch("app.main.backfill_missing_task") as task:
        app = create_app()
        with TestClient(app):
            pass
        task.apply_async.assert_called_once()
