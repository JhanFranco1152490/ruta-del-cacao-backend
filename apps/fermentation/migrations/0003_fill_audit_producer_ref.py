"""Completa el productor de los eventos que ya existían, desde el lote de la fermentación. Un evento cuyo registro ya
no existe y no guardó cómo llegar a su productor queda vacío."""

from django.db import migrations
from django.db.models import OuterRef, Subquery


def fill_producer_ref(apps, schema_editor):
    Event = apps.get_model("fermentation", "FermentationProcessAuditEvent")
    Source = apps.get_model("fermentation", "FermentationProcess")
    producer = Source.objects.filter(pk=OuterRef("process_id")).values(
        "lot__harvest__plot__farm__producer_id"
    )[:1]
    Event.objects.filter(producer_ref__isnull=True).update(producer_ref=Subquery(producer))


class Migration(migrations.Migration):
    dependencies = [
        ("fermentation", "0002_audit_producer_ref"),
        ("lots", "0006_fill_audit_producer_ref"),
    ]

    operations = [migrations.RunPython(fill_producer_ref, migrations.RunPython.noop)]
