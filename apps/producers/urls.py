from rest_framework.routers import SimpleRouter

from .views import ProducerViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("producers", ProducerViewSet, basename="producer")

urlpatterns = router.urls
