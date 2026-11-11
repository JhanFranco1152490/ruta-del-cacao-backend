from django.urls import path

from .views import ProducerIndicatorsView

urlpatterns = [
    path("indicators/producer", ProducerIndicatorsView.as_view(), name="producer-indicators"),
]
