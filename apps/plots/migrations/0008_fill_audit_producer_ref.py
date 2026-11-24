"""Completa el productor de los eventos que ya existían, desde la parcela. Un evento cuyo registro ya
no existe y no guardó cómo llegar a su productor queda vacío."""

from django.db import migrations
from django.db.models import OuterRef, Subquery


def fill_producer_ref(apps, schema_editor):
    Event = apps.get_model("plots", "PlotAuditEvent")
    Plot = apps.get_model("plots", "Plot")
    producer = Plot.objects.filter(pk=OuterRef("plot_ref")).values("farm__producer_id")[:1]
    Event.objects.filter(producer_ref__isnull=True).update(producer_ref=Subquery(producer))


class Migration(migrations.Migration):
    dependencies = [
        ("plots", "0007_audit_producer_ref"),
        ("farms", "0011_fill_audit_producer_ref"),
    ]

    operations = [migrations.RunPython(fill_producer_ref, migrations.RunPython.noop)]
