from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import MonitoringResultView, PestDiseaseViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("pests-diseases", PestDiseaseViewSet, basename="pest-disease")

urlpatterns = [
    path(
        "agricultural-activities/<uuid:pk>/monitoring",
        MonitoringResultView.as_view(),
        name="monitoring-result",
    ),
    *router.urls,
]
