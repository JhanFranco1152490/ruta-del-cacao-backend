from django.urls import path

from .access_switch_views import AssociationAccessView

urlpatterns = [
    path("association-access", AssociationAccessView.as_view(), name="association-access"),
]
