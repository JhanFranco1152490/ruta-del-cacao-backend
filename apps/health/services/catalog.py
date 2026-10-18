from django.db import transaction
from django.db.models import ProtectedError, QuerySet

from apps.common.db import save_translating_unique
from apps.common.text import normalize_catalog_name

from ..exceptions import DuplicatePestDiseaseName, PestDiseaseInUse, PestDiseaseNotFound
from ..models import PestDisease

NAME_UNIQUE_CONSTRAINT = "health_pestdisease_name_unique"
EDITABLE_FIELDS = (
    "name",
    "kind",
    "scientific_name",
    "description",
    "suggested_sampling_unit",
    "suggested_control_method",
    "is_active",
)


def list_pests_diseases(is_active: bool | None = None, search: str | None = None) -> QuerySet:
    pests = PestDisease.objects.order_by("normalized_name", "id")
    if is_active is not None:
        pests = pests.filter(is_active=is_active)
    # Se busca como se comparan los nombres del catálogo, también en el nombre científico:
    # "monilia" encuentra "Monilia" y "roreri" también.
    term = normalize_catalog_name(search or "")
    if term:
        pests = pests.filter(search_normalized__contains=term)
    return pests


def name_taken(name: str, exclude_id=None) -> bool:
    """Si otra plaga o enfermedad ya usa ese nombre, comparado como lo compara el catálogo."""
    others = PestDisease.objects.filter(normalized_name=normalize_catalog_name(name))
    if exclude_id is not None:
        others = others.exclude(pk=exclude_id)
    return others.exists()


@transaction.atomic
def create_pest_disease(data: dict) -> PestDisease:
    # `is_active` solo llega desde el admin; la API registra siempre activas.
    pest = PestDisease(**{name: data[name] for name in EDITABLE_FIELDS if name in data})
    pest.full_clean(validate_unique=False, validate_constraints=False)
    _save(pest)
    return pest


@transaction.atomic
def update_pest_disease(pest_id, data: dict) -> PestDisease:
    """Edita los datos o activa y desactiva. Desactivar no toca los monitoreos que ya la usan:
    solo deja de ofrecerse en los nuevos."""
    pest = PestDisease.objects.select_for_update().filter(pk=pest_id).first()
    if pest is None:
        raise PestDiseaseNotFound()

    before = {name: getattr(pest, name) for name in EDITABLE_FIELDS}
    for name, value in data.items():
        setattr(pest, name, value)
    pest.full_clean(validate_unique=False, validate_constraints=False)
    # Se compara después de validar: un texto que solo cambió en espacios no es un cambio.
    changed = [name for name in before if getattr(pest, name) != before[name]]
    if not changed:
        return pest

    update_fields = [*changed, "updated_at"]
    if "name" in changed:
        update_fields.append("normalized_name")
    if "name" in changed or "scientific_name" in changed:
        update_fields.append("search_normalized")
    _save(pest, update_fields=update_fields)
    return pest


@transaction.atomic
def delete_pest_disease(pest: PestDisease) -> None:
    """Elimina una registrada por error. Una que algún monitoreo usa no se elimina: se
    desactiva."""
    try:
        pest.delete()
    except ProtectedError as error:
        raise PestDiseaseInUse() from error


def _save(pest: PestDisease, update_fields=None) -> None:
    save_translating_unique(
        lambda: pest.save(update_fields=update_fields),
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=DuplicatePestDiseaseName,
    )
