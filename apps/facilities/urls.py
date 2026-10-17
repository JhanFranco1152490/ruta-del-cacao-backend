from rest_framework.routers import SimpleRouter

from .views import PostharvestFacilityViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register(
    "postharvest-facilities", PostharvestFacilityViewSet, basename="postharvest-facility"
)

urlpatterns = router.urls
