from django.db import migrations, models


class Migration(migrations.Migration):
    """El código libre que escribía el productor pasa a ser el nombre opcional de la parcela, y
    el código es el consecutivo que asigna el servidor."""

    dependencies = [
        ("plots", "0005_plot_number_required"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="plot",
            name="plots_farm_code_normalized_unique",
        ),
        migrations.RenameField(model_name="plot", old_name="code", new_name="name"),
        migrations.RenameField(
            model_name="plot", old_name="code_normalized", new_name="name_normalized"
        ),
        migrations.AlterField(
            model_name="plot",
            name="name",
            field=models.CharField(blank=True, max_length=60, null=True),
        ),
        migrations.AlterField(
            model_name="plot",
            name="name_normalized",
            field=models.CharField(editable=False, max_length=200, null=True),
        ),
        migrations.AddConstraint(
            model_name="plot",
            constraint=models.UniqueConstraint(
                fields=("farm", "name_normalized"), name="plots_farm_name_normalized_unique"
            ),
        ),
    ]
