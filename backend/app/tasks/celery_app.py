from celery import Celery

from app.config import get_settings


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "applicator",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["app.tasks.pipeline"],
    )
    app.conf.task_acks_late = True
    app.conf.task_reject_on_worker_lost = True
    app.conf.worker_prefetch_multiplier = 1
    return app


celery_app = make_celery()
