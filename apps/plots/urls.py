from rest_framework.routers import SimpleRouter

from .views import PlotViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("plots", PlotViewSet, basename="plot")

urlpatterns = router.urls
