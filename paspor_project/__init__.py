# Muat aplikasi Celery saat Django start agar `@shared_task` memakai konfigurasi project ini.
from .celery import app as celery_app

__all__ = ("celery_app",)
