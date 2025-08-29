from celery import shared_task
from .views import _run_search_once

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_job_async(self, job_id: str, name: str, hints: dict, pinyin_override: str|None=None):
    _run_search_once(job_id, name, pinyin_override, hints, max_variants=8, pause=0.6)
