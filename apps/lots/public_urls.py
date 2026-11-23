from django.urls import path

from .public_views import PublicLotTraceabilityView

urlpatterns = [
    path(
        "lots/<str:token>",
        PublicLotTraceabilityView.as_view(),
        name="public-lot-traceability",
    ),
]
