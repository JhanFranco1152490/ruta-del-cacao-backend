from django.urls import path

from .views import PostharvestParametersViewSet

# Un recurso por productor, sin id en la ruta: el productor lo dice la sesión.
urlpatterns = [
    path(
        "postharvest-parameters",
        PostharvestParametersViewSet.as_view({"get": "retrieve", "put": "update"}),
        name="postharvest-parameters",
    ),
    path(
        "postharvest-parameters/reset",
        PostharvestParametersViewSet.as_view({"post": "reset"}),
        name="postharvest-parameters-reset",
    ),
]
