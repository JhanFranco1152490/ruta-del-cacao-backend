from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"

    def ready(self):
        # Donde quedan los avisos que calculan las demás apps.
        from apps.common.contracts.alerts import NotificationSink, register_sink

        from .services.create import create_notifications
        from .services.resolve import resolve_notifications, withdraw_notifications

        register_sink(
            NotificationSink(
                create=create_notifications,
                resolve=resolve_notifications,
                withdraw=withdraw_notifications,
            )
        )
