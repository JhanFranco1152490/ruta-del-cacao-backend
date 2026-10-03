"""El contenido de una ficha: lo que se compara para saber si un guardado cambia algo."""

from ..models import PlotCharacterization

# `captured_at` no cuenta: es la hora del dispositivo, y un reintento la trae distinta.
SCALAR_FIELDS = ("planting_date", "stage", "management_system", "shade_type")


def requested_rows(data: dict) -> set[tuple]:
    return {(row["variety_id"], row["tree_count"]) for row in data["varieties"]}


def stored_rows(characterization: PlotCharacterization) -> set[tuple]:
    return {(row.variety_id, row.tree_count) for row in characterization.varieties.all()}


def changed_fields(characterization: PlotCharacterization, data: dict) -> list[str]:
    """Los campos que el guardado cambiaría; vacío si la ficha ya tiene exactamente eso. Las
    filas se comparan como conjunto: el orden en que llegan no es un cambio."""
    changed = [name for name in SCALAR_FIELDS if getattr(characterization, name) != data.get(name)]
    if stored_rows(characterization) != requested_rows(data):
        changed.append("varieties")
    return sorted(changed)
