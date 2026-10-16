from django.urls import path
from rest_framework.routers import SimpleRouter

from .push_views import PushConfigView, PushSubscriptionRemoveView, PushSubscriptionsView
from .views import NotificationViewSet

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("notifications", NotificationViewSet, basename="notification")

# Antes que las del router: `notifications/{id}` también calzaría con estas rutas.
urlpatterns = [
    path("notifications/push-config", PushConfigView.as_view(), name="push-config"),
    path(
        "notifications/push-subscriptions",
        PushSubscriptionsView.as_view(),
        name="push-subscriptions",
    ),
    path(
        "notifications/push-subscriptions/remove",
        PushSubscriptionRemoveView.as_view(),
        name="push-subscriptions-remove",
    ),
    *router.urls,
]
