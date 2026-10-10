from rest_framework.routers import SimpleRouter

from .inventory_views import InputMovementViewSet, InputStockViewSet
from .views import AgriculturalInputViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("agricultural-inputs", AgriculturalInputViewSet, basename="agricultural-input")
router.register("input-stocks", InputStockViewSet, basename="input-stock")
router.register("input-movements", InputMovementViewSet, basename="input-movement")

urlpatterns = router.urls
