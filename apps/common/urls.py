from django.urls import path

from .views import MunicipalityListView

urlpatterns = [
    path("catalogs/municipalities", MunicipalityListView.as_view(), name="municipality-list"),
]
