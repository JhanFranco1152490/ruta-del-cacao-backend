import re
from pathlib import Path

APPS = Path(__file__).resolve().parents[2]
# Lo que nadie debe leer directo: el productor propio del actor. Quien actúa bajo un productor
# (la cuenta técnica) lo hace por `effective_producer_id`; leer el campo deja a esa cuenta sin
# poder operar. `user.producer_id` (la cuenta que se consulta, no la que actúa) no cuenta.
FORBIDDEN = re.compile(r"\b(?:actor|request\.user|self\.request\.user)\.producer_id\b")
# Excepciones explícitas, con su razón. Hoy no hay ninguna.
ALLOWED: dict[str, str] = {}


def test_nobody_reads_the_producer_of_the_actor_directly():
    offenders = []
    for path in APPS.rglob("*.py"):
        relative = path.relative_to(APPS).as_posix()
        if "/tests/" in f"/{relative}" or "/migrations/" in relative or relative in ALLOWED:
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if FORBIDDEN.search(line):
                offenders.append(f"{relative}:{number}: {line.strip()}")

    assert not offenders, "Usa effective_producer_id:\n" + "\n".join(offenders)
