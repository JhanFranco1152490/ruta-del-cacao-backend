import re
from pathlib import Path

APPS = Path(__file__).resolve().parents[2]
RESOURCE_SERVICES = ("farms/services", "plots/services", "crops/services", "inputs/services")
# Buscar algo que ya existe filtrando por el productor del actor deja a la cuenta técnica sin
# alcanzarlo: ella no tiene productor propio. Esos servicios usan `owner_filter` y `owns`
# (`apps/common/ownership.py`), que ya la excluyen de la restricción.
FORBIDDEN = re.compile(r"producer_id[\"']?\s*[=:]\s*actor\.producer_id")
# Excepciones explícitas, con su razón.
ALLOWED: dict[str, str] = {
    "farms/services/scope.py": (
        "`readable_farms` devuelve todas las fincas a la cuenta técnica y a la asociación antes "
        "de llegar a la línea que filtra por el productor propio"
    ),
}


def test_resource_services_do_not_filter_by_the_producer_of_the_actor_directly():
    offenders = []
    for folder in RESOURCE_SERVICES:
        for path in (APPS / folder).rglob("*.py"):
            relative = path.relative_to(APPS).as_posix()
            if relative in ALLOWED:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if FORBIDDEN.search(line):
                    offenders.append(f"{relative}:{number}: {line.strip()}")

    assert not offenders, "Usa owner_filter u owns:\n" + "\n".join(offenders)
