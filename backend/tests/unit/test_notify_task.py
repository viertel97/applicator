import pytest


def _make_fake_post(sent):
    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json

        class R:
            status_code = 200

            def raise_for_status(self):
                pass

        return R()

    return fake_post


def test_notify_task_sends_message(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    sent = {}

    import httpx
    import app.tasks.pipeline as tp
    from contextlib import contextmanager

    monkeypatch.setattr(httpx, "post", _make_fake_post(sent))

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
    assert sent["json"]["text"] == "Done"


def test_notify_task_noop_without_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    called = []

    import httpx

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: called.append(True))

    from app.tasks.pipeline import notify_task

    notify_task({"app_id": "00000000-0000-0000-0000-000000000001"}, chat_id=None)

    assert called == []


def test_notify_task_noop_without_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    called = []

    import httpx

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: called.append(True))

    from app.tasks.pipeline import notify_task

    notify_task({"app_id": "00000000-0000-0000-0000-000000000001"}, chat_id=42)

    assert called == []


def test_notify_task_noop_when_skipped(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    called = []

    import httpx

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: called.append(True))

    from app.tasks.pipeline import notify_task

    notify_task({"app_id": "00000000-0000-0000-0000-000000000001", "skipped": True}, chat_id=42)

    assert called == []
