from rest_framework.routers import SimpleRouter

from .views import QualityViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("quality", QualityViewSet, basename="quality")

urlpatterns = router.urls
