from rest_framework.routers import SimpleRouter

from .log_views import DryingLogViewSet
from .views import DryingViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("drying", DryingViewSet, basename="drying")
router.register("drying/<uuid:lot_id>/logs", DryingLogViewSet, basename="drying-log")

urlpatterns = router.urls
