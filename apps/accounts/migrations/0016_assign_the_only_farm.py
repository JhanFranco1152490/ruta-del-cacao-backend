from collections import defaultdict

from django.db import migrations


def assign_the_only_farm(apps, schema_editor):
    """Los empleados cuyo rol admite una sola finca quedan en la finca de su productor cuando solo
    tiene una. Con varias no hay cómo saber en cuál trabaja cada uno, y un rol que admite varias
    (o todas) puede ser el de un administrador de confianza al que una finca limitaría sin que
    nadie lo decida: quedan sin alcance hasta que el productor los asigne."""
    farms_by_producer = defaultdict(list)
    for producer_id, farm_id in apps.get_model("farms", "Farm").objects.values_list(
        "producer_id", "pk"
    ):
        farms_by_producer[producer_id].append(farm_id)
    only_farm = {
        producer_id: farms[0]
        for producer_id, farms in farms_by_producer.items()
        if len(farms) == 1
    }
    if not only_farm:
        return
    employees = (
        apps.get_model("accounts", "User")
        .objects.filter(
            farms__isnull=True,
            all_farms=False,
            is_superuser=False,
            producer_id__in=only_farm,
            groups__role__farm_scope="one",
        )
        .exclude(groups__role__code="producer")
        .distinct()
    )
    for employee in employees:
        employee.farms.set([only_farm[employee.producer_id]])


def release_farms(apps, schema_editor):
    apps.get_model("accounts", "User").farms.through.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_all_farms_and_role_farm_scope"),
        ("farms", "0005_farm_deletion_and_surviving_audit"),
    ]

    operations = [
        migrations.RunPython(assign_the_only_farm, release_farms),
    ]
