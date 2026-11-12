from django.urls import path

from .views import AssociationReportView, ProducerReportView

urlpatterns = [
    path("reports/producer", ProducerReportView.as_view(), name="producer-report"),
    path("reports/association", AssociationReportView.as_view(), name="association-report"),
]
