from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import DetectionControlsView, MonitoringResultView, PestDiseaseViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("pests-diseases", PestDiseaseViewSet, basename="pest-disease")

urlpatterns = [
    path(
        "agricultural-activities/<uuid:pk>/monitoring",
        MonitoringResultView.as_view(),
        name="monitoring-result",
    ),
    path(
        "phytosanitary-detections/<uuid:pk>/controls",
        DetectionControlsView.as_view(),
        name="detection-controls",
    ),
    *router.urls,
]
