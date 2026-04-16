from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    verbose_name = "Fuel route planning"

    def ready(self) -> None:
        from django.test.signals import setting_changed

        from api.signals import reset_caches_on_setting_change

        # Memoised collaborators must be dropped when their configuration
        # changes, which is exactly what ``override_settings`` does in tests.
        setting_changed.connect(
            reset_caches_on_setting_change,
            dispatch_uid="api.reset_caches_on_setting_change",
            weak=False,
        )
