from rest_framework.routers import SimpleRouter

from .stock_views import StockViewSet
from .warehouse_views import WarehouseViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("warehouses", WarehouseViewSet, basename="warehouse")
router.register("stock", StockViewSet, basename="stock")

urlpatterns = router.urls
