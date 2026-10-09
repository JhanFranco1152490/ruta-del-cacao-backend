from rest_framework.routers import SimpleRouter

from .views import AgriculturalInputViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("agricultural-inputs", AgriculturalInputViewSet, basename="agricultural-input")

urlpatterns = router.urls
