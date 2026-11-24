"""Completa el productor de los eventos que ya existían, desde la cuenta o el rol. Un evento cuyo registro ya
no existe y no guardó cómo llegar a su productor queda vacío."""

from django.db import migrations
from django.db.models import OuterRef, Subquery


def fill_producer_ref(apps, schema_editor):
    Event = apps.get_model("accounts", "AccountManagementEvent")
    User = apps.get_model("accounts", "User")
    Role = apps.get_model("accounts", "Role")
    empty = Event.objects.filter(producer_ref__isnull=True)
    # Una cuenta: su productor; un rol: el suyo (un rol fijo o predefinido no tiene).
    empty.filter(target_user__isnull=False).update(
        producer_ref=Subquery(
            User.objects.filter(pk=OuterRef("target_user_id")).values("producer_id")[:1]
        )
    )
    empty.filter(target_user__isnull=True, target_role_id__isnull=False).update(
        producer_ref=Subquery(
            Role.objects.filter(pk=OuterRef("target_role_id")).values("producer_id")[:1]
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0017_event_producer_ref"),
    ]

    operations = [migrations.RunPython(fill_producer_ref, migrations.RunPython.noop)]
