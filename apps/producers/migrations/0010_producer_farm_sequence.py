from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("producers", "0009_producer_audit_event"),
    ]

    operations = [
        migrations.AddField(
            model_name="producer",
            name="farm_sequence",
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
    ]
