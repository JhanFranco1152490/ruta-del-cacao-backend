from rest_framework.routers import SimpleRouter

from .views import CacaoVarietyViewSet, PlotCharacterizationViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("cacao-varieties", CacaoVarietyViewSet, basename="cacao-variety")
router.register(
    "plot-characterizations", PlotCharacterizationViewSet, basename="plot-characterization"
)

urlpatterns = router.urls
