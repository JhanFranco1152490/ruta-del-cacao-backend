from rest_framework.routers import SimpleRouter

from .views import AgriculturalActivityViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register(
    "agricultural-activities", AgriculturalActivityViewSet, basename="agricultural-activity"
)

urlpatterns = router.urls
