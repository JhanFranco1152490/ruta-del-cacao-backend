import django_filters
from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from .access import is_association_admin
from .models import Role, User


class RoleFilter(django_filters.FilterSet):
    class Meta:
        model = Role
        fields = ["kind", "producer"]


class AccountFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=[("active", "Activo"), ("inactive", "Inactivo")], method="filter_status"
    )
    activation_pending = django_filters.BooleanFilter(method="filter_activation_pending")
    role = django_filters.UUIDFilter(field_name="groups__role__id")
    # Solo lo usa el Administrador; ver filter_producer.
    producer = django_filters.UUIDFilter(method="filter_producer")

    class Meta:
        model = User
        fields = ["status", "activation_pending", "role", "producer"]

    def filter_status(self, queryset, name, value):
        return queryset.filter(is_active=(value == "active"))

    def filter_activation_pending(self, queryset, name, value):
        condition = Q(password__startswith=UNUSABLE_PASSWORD_PREFIX)
        return queryset.filter(condition) if value else queryset.exclude(condition)

    def filter_producer(self, queryset, name, value):
        actor = self.request.user
        if not (actor.is_superuser or is_association_admin(actor)):
            raise ValidationError({"producer": ["Solo el Administrador usa este filtro."]})
        return queryset.filter(producer_id=value)
