import django_filters
from django.db.models import Q

from ..models import Role


class RoleFilter(django_filters.FilterSet):
    # Con `producer`, agrega a los roles de ese productor los del sistema (los que no tienen
    # productor). Sin `producer` no hace nada: no hay a qué agregarlos, ya vienen todos.
    include_system = django_filters.BooleanFilter(method="keep_queryset")

    class Meta:
        model = Role
        fields = ["kind", "producer"]

    def keep_queryset(self, queryset, name, value):
        return queryset

    def filter_queryset(self, queryset):
        data = self.form.cleaned_data
        producer = data.get("producer")
        if not (data.get("include_system") and producer):
            return super().filter_queryset(queryset)
        # `producer` y los roles del sistema son una unión, no dos filtros seguidos (que no
        # dejarían nada): se arma esa unión y se aplican los demás filtros encima.
        queryset = queryset.filter(Q(producer=producer) | Q(producer__isnull=True))
        for name, field_filter in self.filters.items():
            if name in ("producer", "include_system"):
                continue
            queryset = field_filter.filter(queryset, data.get(name))
        return queryset
