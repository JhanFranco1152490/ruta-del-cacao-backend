from django.db.models import Exists, OuterRef, QuerySet

from apps.common.ownership import own_farms, owner_filter, reaches_all_farms
from apps.common.text import normalize_catalog_name

from ..exceptions import InputNotFound
from ..models import AgriculturalInput, InputStock
from ..usage import used_expression

CATALOG_SEARCH_MIN_LENGTH = 2
CATALOG_SEARCH_LIMIT = 20


def readable_inputs(actor) -> QuerySet[AgriculturalInput]:
    """Los insumos que `actor` alcanza: el Productor, todo su catálogo; un empleado, los de la
    fincas en las que trabaja.

    Un insumo es de una finca cuando tiene existencias en ella, aunque estén en cero o se hayan
    agotado. El catálogo se guarda una sola vez por productor; lo que cambia es qué ve cada quien.
    """
    inputs = AgriculturalInput.objects.filter(**owner_filter(actor))
    if not reaches_all_farms(actor):
        # Sin finca asignada no encuentra ninguno. Con `Exists`, un insumo que está en dos de sus
        # fincas sale una sola vez.
        in_own_farm = InputStock.objects.filter(input=OuterRef("pk"), farm__in=own_farms(actor))
        inputs = inputs.filter(Exists(in_own_farm))
    return inputs.select_related("producer").annotate(has_records=used_expression())


def list_inputs(actor, *, producer=None, farm=None) -> QuerySet[AgriculturalInput]:
    """El catálogo que `actor` alcanza. Con `farm`, solo los insumos que están en esa finca: lo que
    se ofrece al registrar una labor de una de sus parcelas. Una finca fuera del alcance no da
    error: simplemente no tiene insumos que mostrar."""
    inputs = readable_inputs(actor)
    # Solo la cuenta técnica elige de qué productor ver: para las demás el alcance ya es el suyo.
    if producer is not None and actor.is_superuser:
        inputs = inputs.filter(producer_id=producer)
    if farm is not None:
        # La finca también debe estar al alcance: si no, uno que está en la suya y en esa otra
        # confirmaría qué hay en una finca donde no trabaja.
        in_farm = InputStock.objects.filter(
            input=OuterRef("pk"),
            farm_id=farm,
            **owner_filter(actor, "farm__producer_id", farm="farm_id"),
        )
        inputs = inputs.filter(Exists(in_farm))
    return inputs.order_by("name_normalized", "id")


def get_input(actor, input_id) -> AgriculturalInput:
    try:
        return readable_inputs(actor).get(pk=input_id)
    except AgriculturalInput.DoesNotExist:
        raise InputNotFound() from None


def search_catalog(actor, term: str) -> QuerySet[AgriculturalInput]:
    """Los insumos activos de todo el catálogo del productor cuyo nombre contiene `term`, para
    traer a una finca uno que ya usa otra al registrarle una entrada.

    Busca por nombre y no entrega el catálogo completo: un empleado encuentra lo que viene a
    registrar sin recorrer lo que hay en las demás fincas. Quien lo sirve entrega solo los datos
    del insumo, nunca cantidades.
    """
    needle = normalize_catalog_name(term)
    if len(needle) < CATALOG_SEARCH_MIN_LENGTH:
        return AgriculturalInput.objects.none()
    return AgriculturalInput.objects.filter(
        **owner_filter(actor), is_active=True, name_normalized__contains=needle
    ).order_by("name_normalized", "id")[:CATALOG_SEARCH_LIMIT]
