from rest_framework.routers import SimpleRouter

from .views import CacaoVarietyViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("cacao-varieties", CacaoVarietyViewSet, basename="cacao-variety")

urlpatterns = router.urls
