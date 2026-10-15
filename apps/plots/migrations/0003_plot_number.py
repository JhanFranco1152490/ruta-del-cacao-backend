from django.db import migrations, models


class Migration(migrations.Migration):
    """Primer paso: la columna admite nulos para poder numerar las parcelas que ya existen."""

    dependencies = [
        ("plots", "0002_plot_deletion_and_surviving_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="plot",
            name="number",
            field=models.PositiveIntegerField(editable=False, null=True),
        ),
    ]
