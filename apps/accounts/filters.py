import django_filters

from .models import Role


class RoleFilter(django_filters.FilterSet):
    class Meta:
        model = Role
        fields = ["kind", "producer"]
