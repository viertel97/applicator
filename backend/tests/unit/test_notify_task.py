import os
import pytest


def test_notify_task_sends_message(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json

        class R:
            status_code = 200
        return R()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)

    # Stub out DB factory so notify_task doesn't need a real DB
    from contextlib import contextmanager
    import app.tasks.pipeline as tp

    @contextmanager
    def fake_cm():
        class FakeDB:
            def get(self, model, pk):
                return None
        yield FakeDB()

    monkeypatch.setattr(tp, "_db_factory", lambda: fake_cm)

    from app.tasks.pipeline import notify_task
    notify_task({"app_id": "00000000-0000-0000-0000-000000000001"}, chat_id=42)

    assert sent["url"] == "https://api.telegram.org/bottest-token/sendMessage"
    assert sent["json"]["chat_id"] == 42


def test_notify_task_noop_without_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    called = []

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: called.append(True))

    from app.tasks.pipeline import notify_task
    notify_task({"app_id": "00000000-0000-0000-0000-000000000001"}, chat_id=None)

    assert called == []


def test_notify_task_noop_without_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    called = []

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: called.append(True))

    from app.tasks.pipeline import notify_task
    notify_task({"app_id": "00000000-0000-0000-0000-000000000001"}, chat_id=42)

    assert called == []
