from django.db import migrations, models


class Migration(migrations.Migration):
    """Primer paso: la columna admite nulos para poder numerar las fincas que ya existen."""

    dependencies = [
        ("farms", "0005_farm_deletion_and_surviving_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="farm",
            name="number",
            field=models.PositiveIntegerField(editable=False, null=True),
        ),
    ]
