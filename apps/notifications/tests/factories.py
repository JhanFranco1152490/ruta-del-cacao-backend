import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.lots.tests.factories import LotFactory
from apps.notifications.choices import NotificationKind
from apps.notifications.models import Notification, PushSubscription


class NotificationFactory(DjangoModelFactory):
    """Un aviso de actividad vencida para el responsable de la actividad."""

    class Meta:
        model = Notification

    activity = factory.SubFactory(AgriculturalActivityFactory)
    recipient = factory.SelfAttribute("activity.assignee")
    kind = NotificationKind.ACTIVITY_OVERDUE
    condition_date = factory.SelfAttribute("activity.scheduled_date")
    condition_key = factory.LazyAttribute(lambda n: f"{n.activity.pk}:{n.condition_date}")
    thread_key = factory.LazyAttribute(lambda n: f"activity:{n.activity.pk}")


class LotNotificationFactory(DjangoModelFactory):
    """Un aviso de volteo pendiente de un lote, para una cuenta de su productor."""

    class Meta:
        model = Notification

    lot = factory.SubFactory(LotFactory)
    recipient = factory.SubFactory(
        UserFactory, producer=factory.SelfAttribute("..lot.harvest.plot.farm.producer")
    )
    kind = NotificationKind.FERMENTATION_TURN_DUE
    condition_key = factory.LazyAttribute(lambda n: f"{n.lot.pk}:turn:1")
    thread_key = factory.LazyAttribute(lambda n: f"lot:{n.lot.pk}")


class PushSubscriptionFactory(DjangoModelFactory):
    class Meta:
        model = PushSubscription

    user = factory.SubFactory(UserFactory)
    endpoint = factory.Sequence(lambda n: f"https://push.example.com/send/{n}")
    p256dh = (
        "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM"
    )
    auth = "tBHItJI5svbpez7KI4CCXg"
