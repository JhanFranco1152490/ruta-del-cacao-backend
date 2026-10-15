from django.db import migrations, models


def foreman_is_one_farm(apps, schema_editor):
    """El Capataz/Operario admite una sola finca. Los roles del sistema se vuelven a sembrar al
    terminar el `migrate`, pero la migración que sigue ya necesita saberlo."""
    apps.get_model("accounts", "Role").objects.filter(code="foreman").update(farm_scope="one")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_user_farms"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="all_farms",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="role",
            name="farm_scope",
            field=models.CharField(
                choices=[
                    ("all", "Siempre todas las fincas"),
                    ("one", "Una sola finca"),
                    ("many", "Una o varias fincas"),
                ],
                default="many",
                max_length=4,
            ),
        ),
        migrations.RunPython(foreman_is_one_farm, migrations.RunPython.noop),
    ]
