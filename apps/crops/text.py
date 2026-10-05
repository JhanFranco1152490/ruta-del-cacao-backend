from apps.common.text import fold

# El guion normal y los que llegan al pegar un nombre copiado de un PDF o de un procesador de
# texto: guion, guion sin salto, cifra, semiraya, raya y signo menos.
DASHES = frozenset("-‐‑‒–—−")


def normalize_variety_name(value: str) -> str:
    """La forma con la que se comparan los nombres del catálogo de variedades: sin mayúsculas,
    tildes, espacios ni guiones, para que `CCN-51`, `CCN 51` y `ccn51` sean la misma.

    No sirve para nombres de fincas o parcelas, donde un espacio interno sí distingue: `La
    Esperanza` no es `LaEsperanza`. Los clones, en cambio, se escriben de las dos formas.
    """
    return "".join(char for char in fold(value) if not char.isspace() and char not in DASHES)
