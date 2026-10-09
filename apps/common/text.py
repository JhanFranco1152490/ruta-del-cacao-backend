import unicodedata


def fold(text: str) -> str:
    """El texto sin tildes ni mayúsculas, para comparar como lo haría una persona: quien escribe
    "cucuta" espera encontrar "Cúcuta"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def normalize_name(value: str) -> str:
    """La forma con la que se compara un nombre propio de un registro (una finca, una parcela)
    para detectar repetidos: sin espacios a los lados ni distinción de mayúsculas."""
    return unicodedata.normalize("NFKC", value.strip()).casefold()


# El guion normal y los que llegan al pegar un nombre copiado de un PDF o de un procesador de
# texto: guion, guion sin salto, cifra, semiraya, raya y signo menos.
DASHES = frozenset("-‐‑‒–—−")


def normalize_catalog_name(value: str) -> str:
    """La forma con la que se comparan los nombres de un catálogo (una variedad, un insumo): sin
    mayúsculas, tildes, espacios ni guiones, para que `CCN-51`, `CCN 51` y `ccn51` sean la misma.

    No sirve para nombres de fincas o parcelas, donde un espacio interno sí distingue: `La
    Esperanza` no es `LaEsperanza`. Los clones y los productos, en cambio, se escriben de las
    dos formas.
    """
    return "".join(char for char in fold(value) if not char.isspace() and char not in DASHES)
