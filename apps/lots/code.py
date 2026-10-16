"""El código de un lote: dice de dónde viene sin abrir el sistema.

    000123-F02-P05-261014-1
    │      │   │   │      └ consecutivo de esa parcela en ese día
    │      │   │   └ fecha de la cosecha (AAMMDD)
    │      │   └ parcela P05 de su finca
    │      └ finca F02 de su productor
    └ productor PROD-000123

Toda parte sale de un dato que no cambia, porque un código impreso no se puede corregir.
"""

from datetime import date

from apps.common.codes import format_code

MEMBER_PREFIX = "PROD-"


def build_lot_code(
    member_code: str, farm_number: int, plot_number: int, harvest_date: date, sequence: int
) -> str:
    return "-".join(
        (
            member_code.removeprefix(MEMBER_PREFIX),
            format_code("F", farm_number),
            format_code("P", plot_number),
            harvest_date.strftime("%y%m%d"),
            str(sequence),
        )
    )
