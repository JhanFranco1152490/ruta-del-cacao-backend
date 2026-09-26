import django_filters

from .models import Producer


class ProducerFilter(django_filters.FilterSet):
    class Meta:
        model = Producer
        fields = ["status", "municipality_code"]
