from rest_framework.routers import SimpleRouter

from .views import SaleViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("sales", SaleViewSet, basename="sale")

urlpatterns = router.urls
