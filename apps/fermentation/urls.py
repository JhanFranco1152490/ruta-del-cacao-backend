from rest_framework.routers import SimpleRouter

from .views import FermentationViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("fermentation", FermentationViewSet, basename="fermentation")

urlpatterns = router.urls
