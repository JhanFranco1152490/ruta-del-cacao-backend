from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    DetectionControlsView,
    DetectionsWithoutControlView,
    EvidenceDetailView,
    EvidenceFileView,
    EvidenceView,
    HistoryView,
    MonitoringResultView,
    NoControlNeededView,
    PestDiseaseViewSet,
)

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("pests-diseases", PestDiseaseViewSet, basename="pest-disease")

urlpatterns = [
    path(
        "agricultural-activities/<uuid:pk>/monitoring",
        MonitoringResultView.as_view(),
        name="monitoring-result",
    ),
    path(
        "phytosanitary-detections/without-control",
        DetectionsWithoutControlView.as_view(),
        name="detections-without-control",
    ),
    path(
        "phytosanitary-detections/<uuid:pk>/no-control-needed",
        NoControlNeededView.as_view(),
        name="detection-no-control-needed",
    ),
    path(
        "phytosanitary-detections/<uuid:pk>/controls",
        DetectionControlsView.as_view(),
        name="detection-controls",
    ),
    path(
        "phytosanitary-history",
        HistoryView.as_view(),
        name="phytosanitary-history",
    ),
    path(
        "agricultural-activities/<uuid:pk>/evidence",
        EvidenceView.as_view(),
        name="activity-evidence",
    ),
    path("evidence/<uuid:pk>", EvidenceDetailView.as_view(), name="evidence-detail"),
    path("evidence/<uuid:pk>/file", EvidenceFileView.as_view(), name="evidence-file"),
    *router.urls,
]
