from rest_framework.routers import SimpleRouter

from .views import AuditLogViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("audit-log", AuditLogViewSet, basename="audit-log")

urlpatterns = router.urls
