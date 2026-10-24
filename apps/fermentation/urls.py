from rest_framework.routers import SimpleRouter

from .turn_views import FermentationTurnViewSet
from .views import FermentationViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("fermentation", FermentationViewSet, basename="fermentation")
router.register(
    "fermentation/<uuid:lot_id>/turns", FermentationTurnViewSet, basename="fermentation-turn"
)

urlpatterns = router.urls
