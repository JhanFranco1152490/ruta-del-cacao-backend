from django.db import migrations


def number_existing_farms(apps, schema_editor):
    # Cada productor numera sus fincas por fecha de creación y, a igualdad, por id, y su contador
    # queda en el último número asignado.
    Farm = apps.get_model("farms", "Farm")
    Producer = apps.get_model("producers", "Producer")
    producers = []
    for producer in Producer.objects.all():
        farms = list(Farm.objects.filter(producer_id=producer.pk).order_by("created_at", "id"))
        for number, farm in enumerate(farms, start=1):
            farm.number = number
        Farm.objects.bulk_update(farms, ["number"])
        producer.farm_sequence = len(farms)
        producers.append(producer)
    Producer.objects.bulk_update(producers, ["farm_sequence"])


class Migration(migrations.Migration):
    """Segundo paso: numera lo existente. Se separa del cambio de esquema porque PostgreSQL no
    deja alterar una tabla con filas modificadas en la misma transacción."""

    dependencies = [
        ("farms", "0006_farm_number"),
        ("producers", "0010_producer_farm_sequence"),
    ]

    operations = [
        migrations.RunPython(number_existing_farms, migrations.RunPython.noop),
    ]
