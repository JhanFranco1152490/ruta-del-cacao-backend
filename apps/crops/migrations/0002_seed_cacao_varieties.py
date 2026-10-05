import unicodedata

from django.db import migrations

# Los clones autorizados como copa por el Consejo Nacional Cacaotero (acuerdo de 2010), según el
# modelo productivo de AGROSAVIA (2020), más los cuatro TCS que AGROSAVIA entregó a la Montaña
# Santandereana entre 2014 y 2017. "Híbrido o común" cubre los árboles de semilla y al productor
# que no sabe qué material tiene: la variedad es obligatoria en la ficha. Los clones que solo se
# autorizan como patrón de injerto no entran: lo que se cosecha es la copa.
INITIAL_VARIETIES = [
    ("CCN-51", "Ecuador", "Autocompatible"),
    ("EET-8", "Ecuador", "Autoincompatible"),
    ("EET-96", "Ecuador", "Autocompatible"),
    ("EET-400", "Ecuador", "Autoincompatible"),
    ("ICS-1", "Trinidad", "Autocompatible"),
    ("ICS-6", "Trinidad", "Autocompatible"),
    ("ICS-39", "Trinidad", "Autoincompatible"),
    ("ICS-40", "Trinidad", "Autoincompatible"),
    ("ICS-60", "Trinidad", "Autoincompatible"),
    ("ICS-95", "Trinidad", "Autocompatible"),
    ("TSH-565", "Trinidad", "Autoincompatible"),
    ("TSH-812", "Trinidad", "Autocompatible"),
    ("UF-650", "Trinidad", "Autoincompatible"),
    ("CAU-39", "Colombia", "Autoincompatible"),
    ("CAU-43", "Colombia", "Autoincompatible"),
    ("FEAR-5", "Colombia (Fedecacao, Arauquita)", "Autocompatible"),
    ("FLE-2", "Colombia", "Autoincompatible"),
    ("FLE-3", "Colombia", "Autoincompatible"),
    ("FSA-11", "Colombia", "Autoincompatible"),
    ("FSA-12", "Colombia", "Autoincompatible"),
    ("FSA-13", "Colombia", "Autoincompatible"),
    ("FTA-2", "Colombia", "Autocompatible"),
    ("SCC-61", "Colombia", "Autoincompatible"),
    ("TCS-01", "Colombia (AGROSAVIA, Montaña Santandereana)", None),
    ("TCS-06", "Colombia (AGROSAVIA, Montaña Santandereana)", None),
    ("TCS-13", "Colombia (AGROSAVIA, Montaña Santandereana)", None),
    ("TCS-19", "Colombia (AGROSAVIA, Montaña Santandereana)", None),
    ("Híbrido o común (sin identificar)", None, None),
]

DASHES = frozenset("-‐‑‒–—−")


def _normalize(name):
    # Copia de la normalización del catálogo: una migración no depende del código vivo, que
    # puede cambiar después sin que esta migración lo sepa.
    decomposed = unicodedata.normalize("NFKD", name)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return "".join(char for char in folded if not char.isspace() and char not in DASHES)


def _description(origin, compatibility):
    parts = []
    if origin:
        parts.append(f"Procedencia: {origin}.")
    if compatibility:
        parts.append(f"{compatibility}.")
    return " ".join(parts)


def add_initial_varieties(apps, schema_editor):
    CacaoVariety = apps.get_model("crops", "CacaoVariety")
    CacaoVariety.objects.bulk_create(
        [
            CacaoVariety(
                name=name,
                name_normalized=_normalize(name),
                description=_description(origin, compatibility),
            )
            for name, origin, compatibility in INITIAL_VARIETIES
        ]
    )


def remove_initial_varieties(apps, schema_editor):
    CacaoVariety = apps.get_model("crops", "CacaoVariety")
    CacaoVariety.objects.filter(
        name_normalized__in=[_normalize(name) for name, _, _ in INITIAL_VARIETIES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("crops", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_initial_varieties, remove_initial_varieties),
    ]
