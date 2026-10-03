import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, OuterRef, Subquery


def copy_plot_reference(apps, schema_editor):
    # Los eventos que ya existen guardan la copia del id y del código de su parcela, para que el
    # historial siga legible si la parcela se elimina después.
    Plot = apps.get_model("plots", "Plot")
    PlotAuditEvent = apps.get_model("plots", "PlotAuditEvent")
    PlotAuditEvent.objects.update(
        plot_ref=F("plot_id"),
        plot_code=Subquery(Plot.objects.filter(pk=OuterRef("plot_id")).values("code")[:1]),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("plots", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="plot",
            options={
                "default_permissions": (),
                "permissions": [
                    ("view_plot", "Puede consultar parcelas"),
                    ("add_plot", "Puede registrar parcelas"),
                    ("change_plot", "Puede editar, activar y desactivar parcelas"),
                    ("delete_plot", "Puede eliminar parcelas creadas por error"),
                ],
            },
        ),
        migrations.AddField(
            model_name="plotauditevent",
            name="plot_ref",
            field=models.UUIDField(db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="plotauditevent",
            name="plot_code",
            field=models.CharField(default="", max_length=50),
        ),
        migrations.RunPython(copy_plot_reference, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="plotauditevent",
            name="plot_ref",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="plotauditevent",
            name="plot_code",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="plotauditevent",
            name="plot",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audit_events",
                to="plots.plot",
            ),
        ),
        migrations.AlterField(
            model_name="plotauditevent",
            name="actor",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="plot_audit_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="plotauditevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("created", "Parcela creada"),
                    ("updated", "Parcela actualizada"),
                    ("status_changed", "Estado de parcela modificado"),
                    ("deleted", "Parcela eliminada"),
                ],
                max_length=32,
            ),
        ),
    ]
