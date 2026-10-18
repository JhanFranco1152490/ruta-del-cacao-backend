from rest_framework.routers import SimpleRouter

from .views import LotViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("lots", LotViewSet, basename="lot")

urlpatterns = router.urls
