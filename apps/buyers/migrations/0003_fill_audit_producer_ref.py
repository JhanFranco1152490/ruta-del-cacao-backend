"""Completa el productor de los eventos que ya existían, desde el comprador. Un evento cuyo registro ya
no existe y no guardó cómo llegar a su productor queda vacío."""

from django.db import migrations
from django.db.models import OuterRef, Subquery


def fill_producer_ref(apps, schema_editor):
    Event = apps.get_model("buyers", "BuyerAuditEvent")
    Source = apps.get_model("buyers", "Buyer")
    producer = Source.objects.filter(pk=OuterRef("buyer_ref")).values("producer_id")[:1]
    Event.objects.filter(producer_ref__isnull=True).update(producer_ref=Subquery(producer))


class Migration(migrations.Migration):
    dependencies = [
        ("buyers", "0002_audit_producer_ref"),
    ]

    operations = [migrations.RunPython(fill_producer_ref, migrations.RunPython.noop)]
