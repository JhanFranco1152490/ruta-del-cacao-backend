from rest_framework.routers import SimpleRouter

from .views import DryingViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("drying", DryingViewSet, basename="drying")

urlpatterns = router.urls
