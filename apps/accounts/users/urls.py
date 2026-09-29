from rest_framework.routers import SimpleRouter

from .views import AccountViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("users", AccountViewSet, basename="account")

urlpatterns = router.urls
