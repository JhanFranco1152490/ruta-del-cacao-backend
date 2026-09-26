import uuid

from django.db import models


class Farm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producer = models.ForeignKey(
        "producers.Producer",
        on_delete=models.PROTECT,
        related_name="farms",
    )
    name = models.CharField(max_length=200)
    name_normalized = models.CharField(max_length=200, editable=False)
    department_code = models.CharField(max_length=2)
    municipality_code = models.CharField(max_length=5)
    details = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    area_hectares = models.DecimalField(max_digits=10, decimal_places=2)
    altitude_masl = models.IntegerField()
    latitude = models.DecimalField(max_digits=9, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["producer", "name_normalized"],
                name="farms_producer_name_normalized_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(area_hectares__gt=0),
                name="farms_area_hectares_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name="farms_latitude_in_range",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lte=180),
                name="farms_longitude_in_range",
            ),
        ]
