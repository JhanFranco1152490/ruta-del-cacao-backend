from rest_framework.routers import SimpleRouter

from .views import BuyerViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("buyers", BuyerViewSet, basename="buyer")

urlpatterns = router.urls
