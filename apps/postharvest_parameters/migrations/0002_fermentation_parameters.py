from decimal import Decimal

from django.db import migrations, models

# Las filas que ya existen toman la línea base de fermentación: el productor no había podido
# cambiarla, así que lo que usaban era eso.
NEW_FIELDS = [
    ("first_turn_hours", models.PositiveSmallIntegerField(default=48)),
    ("next_turn_hours", models.PositiveSmallIntegerField(default=24)),
    (
        "temperature_min_c",
        models.DecimalField(decimal_places=1, max_digits=4, default=Decimal("40.0")),
    ),
    (
        "temperature_max_c",
        models.DecimalField(decimal_places=1, max_digits=4, default=Decimal("50.0")),
    ),
    ("ph_min", models.DecimalField(decimal_places=2, max_digits=4, default=Decimal("4.00"))),
    ("ph_max", models.DecimalField(decimal_places=2, max_digits=4, default=Decimal("5.50"))),
]


def range_check(name, low, high):
    return models.CheckConstraint(
        condition=models.Q((f"{name}__gte", low), (f"{name}__lte", high)),
        name=f"postharvest_params_{name}_range",
    )


def not_above_max(low, high):
    return models.CheckConstraint(
        condition=models.Q((f"{low}__lte", models.F(high))),
        name=f"postharvest_params_{low}_not_above_max",
    )


class Migration(migrations.Migration):
    dependencies = [("postharvest_parameters", "0001_initial")]

    operations = [
        *[
            migrations.AddField(
                model_name="postharvestparameters",
                name=name,
                field=field,
                preserve_default=False,
            )
            for name, field in NEW_FIELDS
        ],
        migrations.AddConstraint(
            model_name="postharvestparameters",
            constraint=range_check("first_turn_hours", 1, 240),
        ),
        migrations.AddConstraint(
            model_name="postharvestparameters",
            constraint=range_check("next_turn_hours", 1, 240),
        ),
        migrations.AddConstraint(
            model_name="postharvestparameters",
            constraint=range_check("temperature_min_c", Decimal("0"), Decimal("80")),
        ),
        migrations.AddConstraint(
            model_name="postharvestparameters",
            constraint=range_check("temperature_max_c", Decimal("0"), Decimal("80")),
        ),
        migrations.AddConstraint(
            model_name="postharvestparameters",
            constraint=range_check("ph_min", Decimal("0"), Decimal("14")),
        ),
        migrations.AddConstraint(
            model_name="postharvestparameters",
            constraint=range_check("ph_max", Decimal("0"), Decimal("14")),
        ),
        migrations.AddConstraint(
            model_name="postharvestparameters",
            constraint=not_above_max("temperature_min_c", "temperature_max_c"),
        ),
        migrations.AddConstraint(
            model_name="postharvestparameters",
            constraint=not_above_max("ph_min", "ph_max"),
        ),
    ]
