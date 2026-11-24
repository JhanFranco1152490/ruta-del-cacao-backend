"""Completa el productor de los eventos que ya existían, desde el insumo. Un evento cuyo registro ya
no existe y no guardó cómo llegar a su productor queda vacío."""

from django.db import migrations
from django.db.models import OuterRef, Subquery


def fill_producer_ref(apps, schema_editor):
    Event = apps.get_model("inputs", "AgriculturalInputAuditEvent")
    AgriculturalInput = apps.get_model("inputs", "AgriculturalInput")
    producer = AgriculturalInput.objects.filter(pk=OuterRef("input_ref")).values("producer_id")[:1]
    Event.objects.filter(producer_ref__isnull=True).update(producer_ref=Subquery(producer))


class Migration(migrations.Migration):
    dependencies = [
        ("inputs", "0003_audit_producer_ref"),
    ]

    operations = [migrations.RunPython(fill_producer_ref, migrations.RunPython.noop)]
