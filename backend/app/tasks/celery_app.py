from celery import Celery


def make_celery() -> Celery:
    # Broker/backend are configured lazily via on_configure signal so that
    # importing this module at test collection time does not require env vars.
    app = Celery(
        "applicator",
        include=["app.tasks.pipeline"],
    )
    app.conf.task_acks_late = True
    app.conf.task_reject_on_worker_lost = True
    app.conf.worker_prefetch_multiplier = 1

    @app.on_after_configure.connect
    def _apply_settings(sender, **kwargs):
        from app.config import get_settings
        settings = get_settings()
        sender.conf.broker_url = settings.celery_broker_url
        sender.conf.result_backend = settings.celery_result_backend

    return app


celery_app = make_celery()
