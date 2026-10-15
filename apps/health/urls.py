from rest_framework.routers import SimpleRouter

from .views import PestDiseaseViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("pests-diseases", PestDiseaseViewSet, basename="pest-disease")

urlpatterns = router.urls
