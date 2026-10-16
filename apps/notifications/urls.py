from rest_framework.routers import SimpleRouter

from .views import NotificationViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = router.urls
