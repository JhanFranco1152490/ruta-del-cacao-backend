from rest_framework.routers import SimpleRouter

from .views import FarmViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("farms", FarmViewSet, basename="farm")

urlpatterns = router.urls
