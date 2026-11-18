from django.urls import path

from .views import (
    AssociationReportFileView,
    AssociationReportView,
    ProducerReportFileView,
    ProducerReportView,
)

urlpatterns = [
    path("reports/producer", ProducerReportView.as_view(), name="producer-report"),
    path("reports/producer/export", ProducerReportFileView.as_view(), name="producer-report-file"),
    path("reports/association", AssociationReportView.as_view(), name="association-report"),
    path(
        "reports/association/export",
        AssociationReportFileView.as_view(),
        name="association-report-file",
    ),
]
