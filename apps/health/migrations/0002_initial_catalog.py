import unicodedata

from django.db import migrations

# Las plagas y enfermedades más comunes del cacao en la región, con la descripción en lenguaje de
# campo: empieza por lo que se ve y dónde, para reconocerla aunque no se recuerde el nombre. La
# asociación las ajusta después desde el catálogo.
INITIAL_CATALOG = [
    (
        "Monilia",
        "disease",
        "Moniliophthora roreri",
        "Solo ataca la mazorca. Empieza con bultos o manchas cafés, como chocolatadas, y termina "
        "cubierta de un polvo blanco crema que contagia a las demás mazorcas.",
    ),
    (
        "Mazorca negra",
        "disease",
        "Phytophthora spp.",
        "Mancha negra o café oscura, húmeda y de borde definido, que crece muy rápido y cubre la "
        "mazorca; los granos se pudren por dentro. También puede atacar cojinetes y tronco.",
    ),
    (
        "Escoba de bruja",
        "disease",
        "Moniliophthora perniciosa",
        "Los brotes se hinchan y echan muchas ramitas juntas, como una escoba, que luego se "
        "secan. Deforma los cojinetes de flores y deja mazorcas duras y secas, parecidas a una "
        "chirimoya.",
    ),
    (
        "Mal del machete",
        "disease",
        "Ceratocystis cacaofunesta (antes C. fimbriata)",
        "Entra por heridas de poda o de herramientas. Las hojas se marchitan de repente y quedan "
        "secas pegadas al árbol, que termina muriendo. En el tronco se ven manchas oscuras en la "
        "madera.",
    ),
    (
        "Rosellinia o pudrición de la raíz",
        "disease",
        "Rosellinia spp.",
        "Ataca las raíces bajo el suelo. El árbol se pone amarillo, se marchita poco a poco y "
        "muere. Al escarbar, las raíces están podridas.",
    ),
    (
        "Monalonion o chinche del cacao",
        "pest",
        "Monalonion dissimulatum",
        "Chinche que pica mazorcas pequeñas y brotes tiernos. Deja puntos o manchas negras; las "
        "mazorcas jóvenes se secan o se deforman.",
    ),
    (
        "Perforador o pasador de la mazorca",
        "pest",
        "Carmenta spp.",
        "Larva de una polilla que perfora la cáscara de la mazorca. Se ven huecos con aserrín y "
        "goma en la superficie.",
    ),
    (
        "Gusanos defoliadores",
        "pest",
        "Dione juno, Eulepidotis spp., entre otros",
        "Orugas de mariposas o polillas que se comen las hojas. Se notan hojas mordidas o "
        "peladas, sobre todo en árboles jóvenes o recién podados.",
    ),
    (
        "Trips",
        "pest",
        "Selenothrips rubrocinctus",
        "Insectos diminutos que raspan el envés de las hojas y la cáscara de la mazorca. Las "
        "hojas se caen y la mazorca se ve oxidada o bronceada, lo que confunde si ya está "
        "madura.",
    ),
    (
        "Cochinilla o piojo blanco",
        "pest",
        "Planococcus citri",
        "Insectos pequeños cubiertos de un polvo blanco como algodón, en el pedúnculo y los "
        "surcos de la mazorca. Chupan savia y atraen hormigas por la melaza que sueltan.",
    ),
    (
        "Barrenadores del tallo",
        "pest",
        "Xyleborus spp.",
        "Escarabajos pequeños que hacen túneles diminutos en el tronco y las ramas; se ven "
        "agujeritos con aserrín fino. Llevan el hongo del mal del machete de un árbol a otro.",
    ),
    (
        "Hormiga arriera",
        "pest",
        "Atta spp.",
        "Hormigas que cortan hojas y brotes y los llevan en fila hasta su nido.",
    ),
]

DASHES = frozenset("-‐‑‒–—−")


def _normalize(text):
    # Copia de la normalización del catálogo: una migración no depende del código vivo, que puede
    # cambiar después sin que esta migración lo sepa.
    decomposed = unicodedata.normalize("NFKD", text)
    folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return "".join(char for char in folded if not char.isspace() and char not in DASHES)


def add_initial_catalog(apps, schema_editor):
    PestDisease = apps.get_model("health", "PestDisease")
    PestDisease.objects.bulk_create(
        [
            PestDisease(
                name=name,
                normalized_name=_normalize(name),
                kind=kind,
                scientific_name=scientific_name,
                description=description,
                search_normalized=f"{_normalize(name)}|{_normalize(scientific_name)}",
            )
            for name, kind, scientific_name, description in INITIAL_CATALOG
        ]
    )


def remove_initial_catalog(apps, schema_editor):
    PestDisease = apps.get_model("health", "PestDisease")
    PestDisease.objects.filter(
        normalized_name__in=[_normalize(name) for name, _, _, _ in INITIAL_CATALOG]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("health", "0001_initial")]

    operations = [migrations.RunPython(add_initial_catalog, remove_initial_catalog)]
