from rest_framework.response import Response

from apps.common.pagination import StandardPagination

COUNT_SCHEMA = {"type": "integer", "minimum": 0}


class PlotPagination(StandardPagination):
    """La paginación común, más cuántas parcelas tienen ficha y cuántas no en todas las páginas.

    Los conteos los calcula quien pagina: no dependen del filtro de caracterización, así que con
    el filtro "sin ficha" puesto el contador sigue diciendo cuántas de todas están caracterizadas.
    """

    def get_paginated_response(self, data, characterization_counts):
        return Response(
            {
                "count": self.page.paginator.count,
                "characterization_counts": characterization_counts,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema):
        paginated = super().get_paginated_response_schema(schema)
        paginated["properties"]["characterization_counts"] = {
            "type": "object",
            "properties": {"done": COUNT_SCHEMA, "pending": COUNT_SCHEMA},
            "required": ["done", "pending"],
        }
        paginated["required"] = [*paginated.get("required", []), "characterization_counts"]
        return paginated
