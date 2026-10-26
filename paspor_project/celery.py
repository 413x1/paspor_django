"""Aplikasi Celery PASPOR. Dimuat otomatis lewat `paspor_project/__init__.py`.

Menjalankan worker/beat (dari root project):
    celery -A paspor_project worker -l info -Q default,email
    celery -A paspor_project beat -l info
Lihat wiki/instructions/CELERY_IMPLEMENTATION_PLAN.MD.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "paspor_project.settings")

app = Celery("paspor_project")
app.config_from_object("django.conf:settings", namespace="CELERY")   # baca setting berawalan CELERY_
app.autodiscover_tasks()                                             # cari tasks.py di tiap app terpasang
