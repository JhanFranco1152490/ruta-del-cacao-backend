from django.contrib import admin

from apps.common.admin import SuperuserReadOnlyAdminMixin

from .models import Notification, PushSubscription


@admin.register(Notification)
class NotificationAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Los avisos de cada persona, de solo lectura: los crea la evaluación y cada persona los lee
    o los elimina desde la aplicación."""

    list_display = ("kind", "recipient", "created_at", "read_at", "dismissed_at", "pushed_at")
    list_filter = ("kind", "severity")
    list_select_related = ("recipient",)
    readonly_fields = (
        "recipient",
        "kind",
        "severity",
        "condition_key",
        "thread_key",
        "activity",
        "condition_date",
        "created_at",
        "read_at",
        "dismissed_at",
        "pushed_at",
    )


@admin.register(PushSubscription)
class PushSubscriptionAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Los dispositivos con las push activadas, de solo lectura. No muestra la dirección ni las
    llaves: con ellas se le pueden mandar avisos a ese dispositivo."""

    list_display = ("user", "device_label", "created_at", "last_success_at")
    list_select_related = ("user",)
    fields = ("user", "device_label", "created_at", "last_success_at")
    readonly_fields = fields
