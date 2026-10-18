from rest_framework.routers import SimpleRouter

from .views import HarvestViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("harvests", HarvestViewSet, basename="harvest")

urlpatterns = router.urls
