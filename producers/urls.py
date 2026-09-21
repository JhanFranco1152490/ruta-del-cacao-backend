from django.urls import path

from .views import ProducerDetailView, ProducerListCreateView, ProducerStatusView

urlpatterns = [
    path("", ProducerListCreateView.as_view()),
    path("<uuid:producer_id>", ProducerDetailView.as_view()),
    path("<uuid:producer_id>/status", ProducerStatusView.as_view()),
]
