from django.db import migrations

# Qué se cuenta para medir cada una del catálogo inicial y, donde la práctica es clara, qué control
# se suele aplicar. Es un punto de partida que la asociación ajusta desde el catálogo; por eso solo
# se llena lo que sigue vacío y nunca se pisa una elección hecha.
# nombre: (unidad, control)
SUGGESTIONS = {
    "Monilia": ("pods", "fruit_removal"),
    "Mazorca negra": ("pods", "fruit_removal"),
    "Escoba de bruja": ("trees", "sanitary_pruning"),
    "Mal del machete": ("trees", None),
    "Rosellinia o pudrición de la raíz": ("trees", None),
    "Monalonion o chinche del cacao": ("pods", None),
    "Perforador o pasador de la mazorca": ("pods", None),
    "Gusanos defoliadores": ("trees", None),
    "Trips": ("trees", None),
    "Cochinilla o piojo blanco": ("pods", None),
    "Barrenadores del tallo": ("trees", None),
    "Hormiga arriera": ("trees", None),
}


def add_suggestions(apps, schema_editor):
    PestDisease = apps.get_model("health", "PestDisease")
    for name, (unit, method) in SUGGESTIONS.items():
        pest = PestDisease.objects.filter(name=name).first()
        if pest is None:
            continue
        if pest.suggested_sampling_unit is None:
            pest.suggested_sampling_unit = unit
        if pest.suggested_control_method is None:
            pest.suggested_control_method = method
        pest.save(update_fields=["suggested_sampling_unit", "suggested_control_method"])


class Migration(migrations.Migration):
    dependencies = [("health", "0006_pest_suggestions")]

    operations = [migrations.RunPython(add_suggestions, migrations.RunPython.noop)]
