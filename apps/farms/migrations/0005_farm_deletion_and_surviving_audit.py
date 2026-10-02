import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, OuterRef, Subquery


def copy_farm_reference(apps, schema_editor):
    # Los eventos que ya existen guardan la copia del id y del nombre de su finca, para que el
    # historial siga legible si la finca se elimina después.
    Farm = apps.get_model("farms", "Farm")
    FarmAuditEvent = apps.get_model("farms", "FarmAuditEvent")
    FarmAuditEvent.objects.update(
        farm_ref=F("farm_id"),
        farm_name=Subquery(Farm.objects.filter(pk=OuterRef("farm_id")).values("name")[:1]),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("farms", "0004_farm_permission_names"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="farm",
            options={
                "default_permissions": (),
                "permissions": [
                    ("view_farm", "Puede consultar fincas"),
                    ("add_farm", "Puede registrar fincas"),
                    ("change_farm", "Puede editar, activar y desactivar fincas"),
                    ("delete_farm", "Puede eliminar fincas creadas por error"),
                ],
            },
        ),
        migrations.AddField(
            model_name="farmauditevent",
            name="farm_ref",
            field=models.UUIDField(db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="farmauditevent",
            name="farm_name",
            field=models.CharField(default="", max_length=200),
        ),
        migrations.RunPython(copy_farm_reference, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="farmauditevent",
            name="farm_ref",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="farmauditevent",
            name="farm_name",
            field=models.CharField(max_length=200),
        ),
        migrations.AlterField(
            model_name="farmauditevent",
            name="farm",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audit_events",
                to="farms.farm",
            ),
        ),
        migrations.AlterField(
            model_name="farmauditevent",
            name="actor",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="farm_audit_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="farmauditevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("created", "Finca creada"),
                    ("updated", "Finca actualizada"),
                    ("status_changed", "Estado de finca modificado"),
                    ("deleted", "Finca eliminada"),
                ],
                max_length=32,
            ),
        ),
    ]
