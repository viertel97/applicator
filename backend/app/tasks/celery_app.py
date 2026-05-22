from celery import Celery

from app.config import get_settings


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "applicator",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=[
            "app.tasks.pipeline",
            "app.tasks.check_postings",
            "app.tasks.backfill",
            "app.tasks.categorize_labels",
        ],
    )
    app.conf.task_acks_late = True
    app.conf.task_reject_on_worker_lost = True
    app.conf.worker_prefetch_multiplier = 1
    app.conf.timezone = "UTC"
    app.conf.beat_schedule = {
        "check-postings-every-6h": {
            "task": "tasks.check_postings",
            "schedule": 21600.0,
        },
    }
    return app


celery_app = make_celery()
