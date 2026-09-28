from django.urls import path

from .views import AssociationAccessView

urlpatterns = [
    path("association-access", AssociationAccessView.as_view(), name="association-access"),
]
