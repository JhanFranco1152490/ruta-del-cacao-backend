import unicodedata


def fold(text: str) -> str:
    """El texto sin tildes ni mayúsculas, para comparar como lo haría una persona: quien escribe
    "cucuta" espera encontrar "Cúcuta"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
