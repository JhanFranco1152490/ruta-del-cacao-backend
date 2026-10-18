from django.db import migrations, models


class Migration(migrations.Migration):
    """Tercer paso: con todas las fincas numeradas, el número es obligatorio y único por productor."""

    dependencies = [
        ("farms", "0007_number_existing_farms"),
    ]

    operations = [
        migrations.AlterField(
            model_name="farm",
            name="number",
            field=models.PositiveIntegerField(editable=False),
        ),
        migrations.AddConstraint(
            model_name="farm",
            constraint=models.UniqueConstraint(
                fields=("producer", "number"), name="farms_producer_number_unique"
            ),
        ),
    ]
