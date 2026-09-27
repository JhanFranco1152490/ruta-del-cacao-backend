from django.urls import path
from rest_framework.routers import SimpleRouter

from .role_views import PermissionCatalogView, RoleViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("roles", RoleViewSet, basename="role")

urlpatterns = [
    *router.urls,
    path("permissions", PermissionCatalogView.as_view(), name="permission-list"),
]
