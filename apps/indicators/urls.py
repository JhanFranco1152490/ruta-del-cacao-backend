from django.urls import path

from .views import AssociationIndicatorsView, ProducerIndicatorsView

urlpatterns = [
    path("indicators/producer", ProducerIndicatorsView.as_view(), name="producer-indicators"),
    path(
        "indicators/association",
        AssociationIndicatorsView.as_view(),
        name="association-indicators",
    ),
]
