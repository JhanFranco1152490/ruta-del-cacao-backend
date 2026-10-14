from collections import defaultdict

from django.db import migrations

# Las apps de lo que cuelga de una finca, como estaban al escribir esta migración: una migración
# no lee el registro de permisos del código, que puede cambiar después. El único permiso de estas
# apps que no es de una finca (el catálogo de variedades) lo tiene la asociación, cuyas cuentas no
# tienen productor y por eso no entran aquí.
FIELD_APPS = ("farms", "plots", "crops", "inputs", "activities")
# Lo que deja de poder delegarse: registrar fincas es solo del Productor.
PRODUCER_ONLY = (("farms", "add_farm"),)


def assign_the_only_farm(apps, schema_editor):
    """Los empleados con permisos de campo quedan en la finca de su productor cuando solo tiene
    una. Con varias no hay cómo saber en cuál trabaja cada uno: quedan sin finca hasta que el
    productor los asigne."""
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
            is_superuser=False,
            producer_id__in=only_farm,
            groups__permissions__content_type__app_label__in=FIELD_APPS,
        )
        .exclude(groups__role__code="producer")
        .distinct()
    )
    for employee in employees:
        employee.farms.set([only_farm[employee.producer_id]])


def release_farms(apps, schema_editor):
    apps.get_model("accounts", "User").farms.through.objects.all().delete()


def keep_registering_farms_with_the_producer(apps, schema_editor):
    """Registrar fincas deja de poder delegarse: se retira de los roles propios que lo
    tenían. Los roles del sistema se vuelven a armar solos después de migrar."""
    permission_model = apps.get_model("auth", "Permission")
    permissions = [
        permission
        for app_label, codename in PRODUCER_ONLY
        if (
            permission := permission_model.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).first()
        )
        is not None
    ]
    if not permissions:
        return
    custom_roles = apps.get_model("accounts", "Role").objects.filter(kind="custom")
    for role in custom_roles.select_related("group"):
        role.group.permissions.remove(*permissions)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_user_farms"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("farms", "0005_farm_deletion_and_surviving_audit"),
    ]

    operations = [
        migrations.RunPython(assign_the_only_farm, release_farms),
        migrations.RunPython(keep_registering_farms_with_the_producer, migrations.RunPython.noop),
    ]
