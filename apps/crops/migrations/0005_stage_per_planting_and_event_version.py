import unicodedata

from django.db import migrations, models

DASHES = frozenset("-‐‑‒–—−")

# La única variedad de semilla del catálogo inicial: las demás son clones, que se injertan.
SEED_VARIETY = "Híbrido o común (sin identificar)"

STAGES = [
    ("establishment", "Establecimiento o formación"),
    ("early_production", "Inicio de producción"),
    ("full_production", "Producción estable"),
    ("renovation", "Renovación o rehabilitación"),
]
PROPAGATIONS = [("grafted", "Injerto o clon"), ("seed", "Semilla")]


def _normalize(name):
    # Copia de la normalización del catálogo: una migración no depende del código vivo.
    decomposed = unicodedata.normalize("NFKD", name)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return "".join(char for char in folded if not char.isspace() and char not in DASHES)


def move_stage_to_plantings(apps, schema_editor):
    # Antes la etapa era de la ficha: cada una de sus siembras pasa a tener esa etapa, y la
    # propagación se deduce de la variedad.
    PlotPlanting = apps.get_model("crops", "PlotPlanting")
    seed = _normalize(SEED_VARIETY)
    for planting in PlotPlanting.objects.select_related("characterization", "variety"):
        planting.stage = planting.characterization.stage
        planting.propagation = "seed" if planting.variety.name_normalized == seed else "grafted"
        planting.save(update_fields=["stage", "propagation"])


def move_stage_back_to_characterizations(apps, schema_editor):
    # Al revertir, la ficha vuelve a tener una sola etapa: la de su siembra con más árboles (y, a
    # igualdad, la más antigua).
    PlotCharacterization = apps.get_model("crops", "PlotCharacterization")
    for characterization in PlotCharacterization.objects.all():
        main = characterization.plantings.order_by("-tree_count", "planting_date").first()
        characterization.stage = main.stage if main else "establishment"
        characterization.save(update_fields=["stage"])


def number_existing_events(apps, schema_editor):
    # Los eventos que ya existen no guardaban su versión: se numeran por su orden en cada
    # parcela, que es el orden en que la ficha fue subiendo de versión. Sus valores también pasan
    # a la forma nueva: la etapa y la propagación van en cada siembra y no en la ficha.
    Event = apps.get_model("crops", "PlotCharacterizationAuditEvent")
    Variety = apps.get_model("crops", "CacaoVariety")
    seed_ids = {
        str(pk)
        for pk in Variety.objects.filter(name_normalized=_normalize(SEED_VARIETY)).values_list(
            "pk", flat=True
        )
    }
    counters = {}
    for event in Event.objects.order_by("plot_id", "occurred_at", "id"):
        counters[event.plot_id] = counters.get(event.plot_id, 0) + 1
        event.version = counters[event.plot_id]
        event.snapshot = _snapshot_with_stage_per_planting(event.snapshot, seed_ids)
        event.save(update_fields=["version", "snapshot"])


def _snapshot_with_stage_per_planting(snapshot, seed_ids):
    if "stage" not in snapshot:
        return snapshot
    stage = snapshot["stage"]
    converted = {key: value for key, value in snapshot.items() if key != "stage"}
    converted["plantings"] = [
        {
            **row,
            "stage": stage,
            "propagation": "seed" if row.get("variety_id") in seed_ids else "grafted",
        }
        for row in snapshot.get("plantings", [])
    ]
    return converted


class Migration(migrations.Migration):
    dependencies = [
        ("crops", "0004_seed_common_names"),
    ]

    operations = [
        # La etapa y la propagación pasan a cada siembra.
        migrations.AddField(
            model_name="plotplanting",
            name="propagation",
            field=models.CharField(choices=PROPAGATIONS, max_length=16, null=True),
        ),
        migrations.AddField(
            model_name="plotplanting",
            name="stage",
            field=models.CharField(choices=STAGES, max_length=32, null=True),
        ),
        migrations.RunPython(move_stage_to_plantings, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="plotplanting",
            name="propagation",
            field=models.CharField(choices=PROPAGATIONS, max_length=16),
        ),
        migrations.AlterField(
            model_name="plotplanting",
            name="stage",
            field=models.CharField(choices=STAGES, max_length=32),
        ),
        migrations.AlterField(
            model_name="plotcharacterization",
            name="stage",
            field=models.CharField(choices=STAGES, max_length=32, null=True),
        ),
        migrations.RunPython(migrations.RunPython.noop, move_stage_back_to_characterizations),
        migrations.RemoveField(model_name="plotcharacterization", name="stage"),
        # Cada evento del historial guarda la versión de la ficha que dejó.
        migrations.AddField(
            model_name="plotcharacterizationauditevent",
            name="version",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.RunPython(number_existing_events, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="plotcharacterizationauditevent",
            name="version",
            field=models.PositiveIntegerField(),
        ),
    ]
