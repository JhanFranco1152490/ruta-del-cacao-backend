import django_filters
from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from ..access import is_association_admin
from ..models import User
from .farm_assignment import employees_without_scope


class AccountFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=[("active", "Activo"), ("inactive", "Inactivo")], method="filter_status"
    )
    activation_pending = django_filters.BooleanFilter(method="filter_activation_pending")
    role = django_filters.UUIDFilter(field_name="groups__role__id")
    # Solo lo usa el Administrador; ver filter_producer.
    producer = django_filters.UUIDFilter(method="filter_producer")
    municipality = django_filters.CharFilter(field_name="producer__municipality_code")
    farm = django_filters.UUIDFilter(method="filter_farm")
    # Los empleados a los que les falta alcance: sin fincas y sin «todas las fincas».
    without_farm = django_filters.BooleanFilter(method="filter_without_farm")

    class Meta:
        model = User
        fields = [
            "status",
            "activation_pending",
            "role",
            "producer",
            "municipality",
            "farm",
            "without_farm",
        ]

    def filter_farm(self, queryset, name, value):
        # Quien trabaja en todas las fincas también trabaja en esta.
        return queryset.filter(
            pk__in=User.objects.filter(Q(farms=value) | Q(all_farms=True)).values("pk")
        )

    def filter_without_farm(self, queryset, name, value):
        missing = queryset.filter(pk__in=employees_without_scope())
        return missing if value else queryset.exclude(pk__in=missing.values("pk"))

    def filter_status(self, queryset, name, value):
        # Por el estado efectivo: la cuenta de un productor inactivo no tiene acceso aunque la
        # cuenta esté activa, así que cuenta entre las inactivas.
        effectively_active = Q(is_active=True) & (
            Q(producer__isnull=True) | Q(producer__status="active")
        )
        if value == "active":
            return queryset.filter(effectively_active)
        return queryset.exclude(effectively_active)

    def filter_activation_pending(self, queryset, name, value):
        condition = Q(password__startswith=UNUSABLE_PASSWORD_PREFIX)
        return queryset.filter(condition) if value else queryset.exclude(condition)

    def filter_producer(self, queryset, name, value):
        actor = self.request.user
        if not (actor.is_superuser or is_association_admin(actor)):
            raise ValidationError({"producer": ["Solo el Administrador usa este filtro."]})
        return queryset.filter(producer_id=value)
