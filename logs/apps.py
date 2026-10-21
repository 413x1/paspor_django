from django.apps import AppConfig


class LogsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "logs"
    verbose_name = "Log Sistem"

    def ready(self):
        from . import signals  # noqa: F401  (mendaftarkan receiver login/logout)
