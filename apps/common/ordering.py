from django.db.models import F
from rest_framework.filters import OrderingFilter

PRODUCER_KEY = "producer"


class ProducerOrderingFilter(OrderingFilter):
    """Agrega `ordering=producer`: por el código de asociado del productor.

    Ordenar por la clave foránea sería ordenar por un UUID sin significado. Lo que no tiene
    productor va primero (y último al invertir): son las cuentas y roles de la asociación, y la
    vista agrupada los muestra antes que los de cada productor.
    """

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view)
        if not ordering:
            return queryset
        return queryset.order_by(*(self._term(item) for item in ordering))

    @staticmethod
    def _term(item: str):
        if item.lstrip("-") != PRODUCER_KEY:
            return item
        column = F("producer__member_code")
        return (
            column.desc(nulls_last=True) if item.startswith("-") else column.asc(nulls_first=True)
        )
