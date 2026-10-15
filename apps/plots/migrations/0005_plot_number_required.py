from django.db import migrations, models


class Migration(migrations.Migration):
    """Tercer paso: con todas las parcelas numeradas, el número es obligatorio y único por finca."""

    dependencies = [
        ("plots", "0004_number_existing_plots"),
    ]

    operations = [
        migrations.AlterField(
            model_name="plot",
            name="number",
            field=models.PositiveIntegerField(editable=False),
        ),
        migrations.AddConstraint(
            model_name="plot",
            constraint=models.UniqueConstraint(
                fields=("farm", "number"), name="plots_farm_number_unique"
            ),
        ),
    ]
