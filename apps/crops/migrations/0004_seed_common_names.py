import unicodedata

from django.db import migrations

DASHES = frozenset("-‐‑‒–—−")

# Las siglas de los clones colombianos dicen dónde se seleccionaron, y así se les llama en campo:
# FSA es Fedecacao Saravena, FLE Fedecacao Lebrija, FTA Fedecacao Tame, FEAR Fedecacao Arauquita,
# FSV Fedecacao San Vicente, CAU Caucasia, SCC Selección Colombia Corpoica (de San Vicente de
# Chucurí) y TCS Theobroma Corpoica La Suiza. De un mismo lugar salen varios clones, así que un
# nombre común se repite entre variedades. Los clones internacionales se conocen por su código.
COMMON_NAMES = {
    "CCN-51": ["Colección Castro Naranjal"],
    "CAU-39": ["Caucasia"],
    "CAU-43": ["Caucasia"],
    "FEAR-5": ["Arauquita", "Fedecacao Arauquita"],
    "FLE-2": ["Lebrija", "Fedecacao Lebrija"],
    "FLE-3": ["Lebrija", "Fedecacao Lebrija"],
    "FSA-11": ["Saravena", "Fedecacao Saravena"],
    "FSA-12": ["Saravena", "Fedecacao Saravena"],
    "FSA-13": ["Saravena", "Fedecacao Saravena"],
    "FTA-2": ["Tame", "Fedecacao Tame"],
    "SCC-61": ["San Vicente", "Selección Colombia Corpoica"],
    "FSV-41": ["San Vicente", "Fedecacao San Vicente"],
    "TCS-01": ["La Suiza", "Theobroma Corpoica La Suiza"],
    "TCS-06": ["La Suiza", "Theobroma Corpoica La Suiza"],
    "TCS-13": ["La Suiza", "Theobroma Corpoica La Suiza"],
    "TCS-19": ["La Suiza", "Theobroma Corpoica La Suiza"],
}

# Clon regional de Fedecacao posterior a la lista de 2010 de clones autorizados, muy sembrado en
# Santander. Su compatibilidad no se encontró en una fuente confiable.
FSV_41 = ("FSV-41", "Procedencia: Colombia (Fedecacao, San Vicente de Chucurí).")


def _normalize(name):
    # Copia de la normalización del catálogo: una migración no depende del código vivo.
    decomposed = unicodedata.normalize("NFKD", name)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return "".join(char for char in folded if not char.isspace() and char not in DASHES)


def _search_text(name, common_names):
    return "|".join(_normalize(text) for text in [name, *common_names])


def add_common_names(apps, schema_editor):
    CacaoVariety = apps.get_model("crops", "CacaoVariety")
    name, description = FSV_41
    # La asociación pudo haberla registrado ya: no se duplica.
    CacaoVariety.objects.get_or_create(
        name_normalized=_normalize(name),
        defaults={"name": name, "description": description},
    )
    for variety in CacaoVariety.objects.filter(
        name_normalized__in=[_normalize(name) for name in COMMON_NAMES]
    ):
        # Solo si la asociación no los llenó: lo que ella escribió vale más.
        if not variety.common_names:
            variety.common_names = COMMON_NAMES[
                next(key for key in COMMON_NAMES if _normalize(key) == variety.name_normalized)
            ]
        variety.search_normalized = _search_text(variety.name, variety.common_names)
        variety.save(update_fields=["common_names", "search_normalized"])


def remove_common_names(apps, schema_editor):
    CacaoVariety = apps.get_model("crops", "CacaoVariety")
    CacaoVariety.objects.filter(
        name_normalized=_normalize(FSV_41[0]), plantings__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("crops", "0003_plantings_and_common_names"),
    ]

    operations = [
        migrations.RunPython(add_common_names, remove_common_names),
    ]
