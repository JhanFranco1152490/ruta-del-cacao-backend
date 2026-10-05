import unicodedata

import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models

DASHES = frozenset("-‐‑‒–—−")


def _normalize(name):
    # Copia de la normalización del catálogo: una migración no depende del código vivo.
    decomposed = unicodedata.normalize("NFKD", name)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return "".join(char for char in folded if not char.isspace() and char not in DASHES)


def copy_planting_date_to_plantings(apps, schema_editor):
    # Antes había una sola fecha por ficha: cada una de sus filas pasa a ser una siembra de esa
    # fecha.
    PlotPlanting = apps.get_model("crops", "PlotPlanting")
    for planting in PlotPlanting.objects.select_related("characterization"):
        planting.planting_date = planting.characterization.planting_date
        planting.save(update_fields=["planting_date"])


def copy_first_planting_date_back(apps, schema_editor):
    # Al revertir, la ficha vuelve a tener una sola fecha: la de su siembra más antigua.
    PlotCharacterization = apps.get_model("crops", "PlotCharacterization")
    for characterization in PlotCharacterization.objects.all():
        first = characterization.plantings.order_by("planting_date").first()
        characterization.planting_date = first.planting_date if first else None
        characterization.save(update_fields=["planting_date"])


def fill_search_text(apps, schema_editor):
    CacaoVariety = apps.get_model("crops", "CacaoVariety")
    for variety in CacaoVariety.objects.all():
        variety.search_normalized = _normalize(variety.name)
        variety.save(update_fields=["search_normalized"])


class Migration(migrations.Migration):
    dependencies = [
        ("crops", "0002_seed_cacao_varieties"),
    ]

    operations = [
        # Las filas de la ficha pasan a ser siembras: variedad, fecha y árboles.
        migrations.RenameModel("PlotCharacterizationVariety", "PlotPlanting"),
        migrations.RemoveConstraint(
            model_name="plotplanting", name="crops_characterization_variety_unique"
        ),
        migrations.AlterField(
            model_name="plotplanting",
            name="characterization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="plantings",
                to="crops.plotcharacterization",
            ),
        ),
        migrations.AlterField(
            model_name="plotplanting",
            name="variety",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plantings",
                to="crops.cacaovariety",
            ),
        ),
        migrations.AddField(
            model_name="plotplanting",
            name="planting_date",
            field=models.DateField(null=True),
        ),
        migrations.RunPython(copy_planting_date_to_plantings, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="plotplanting",
            name="planting_date",
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name="plotcharacterization",
            name="planting_date",
            field=models.DateField(null=True),
        ),
        migrations.RunPython(migrations.RunPython.noop, copy_first_planting_date_back),
        migrations.RemoveConstraint(
            model_name="plotcharacterization", name="crops_planting_date_first_of_month"
        ),
        migrations.RemoveField(model_name="plotcharacterization", name="planting_date"),
        migrations.AddConstraint(
            model_name="plotplanting",
            constraint=models.UniqueConstraint(
                fields=("characterization", "variety", "planting_date"),
                name="crops_planting_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="plotplanting",
            constraint=models.CheckConstraint(
                condition=models.Q(("planting_date__day", 1)),
                name="crops_planting_date_first_of_month",
            ),
        ),
        migrations.AddField(
            model_name="cacaovariety",
            name="common_names",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=60),
                blank=True,
                default=list,
                size=5,
            ),
        ),
        migrations.AddField(
            model_name="cacaovariety",
            name="search_normalized",
            field=models.TextField(default="", editable=False),
        ),
        migrations.RunPython(fill_search_text, migrations.RunPython.noop),
    ]
