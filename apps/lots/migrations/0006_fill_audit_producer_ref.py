"""Completa el productor de los eventos que ya existían, desde la cosecha del lote. Un evento cuyo registro ya
no existe y no guardó cómo llegar a su productor queda vacío."""

from django.db import migrations
from django.db.models import OuterRef, Subquery


def fill_producer_ref(apps, schema_editor):
    Event = apps.get_model("lots", "LotAuditEvent")
    Source = apps.get_model("harvests", "Harvest")
    producer = Source.objects.filter(pk=OuterRef("harvest_ref")).values("plot__farm__producer_id")[
        :1
    ]
    Event.objects.filter(producer_ref__isnull=True).update(producer_ref=Subquery(producer))


class Migration(migrations.Migration):
    dependencies = [
        ("lots", "0005_audit_producer_ref"),
        ("harvests", "0003_fill_audit_producer_ref"),
    ]

    operations = [migrations.RunPython(fill_producer_ref, migrations.RunPython.noop)]
