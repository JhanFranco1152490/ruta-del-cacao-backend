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
