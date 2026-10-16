from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("farms", "0008_farm_number_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="farm",
            name="plot_sequence",
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
    ]
