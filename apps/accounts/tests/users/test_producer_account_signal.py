import pytest

from apps.accounts.models import User
from apps.accounts.system_roles import PRODUCER
from apps.accounts.users.services import create_producer_account_automatically
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def test_saving_a_new_producer_creates_its_account():
    producer = ProducerFactory(email="ana@example.com")

    user = User.objects.get(producer=producer)
    assert user.groups.filter(role__code=PRODUCER).exists()
    assert not user.has_usable_password()


def test_a_producer_without_email_gets_no_account():
    producer = ProducerFactory()  # sin correo: el valor por defecto de la fábrica

    assert not User.objects.filter(producer=producer).exists()


def test_editing_a_producer_does_not_create_a_second_account():
    producer = ProducerFactory(email="ana@example.com")

    producer.first_name = "Cambiado"
    producer.save(update_fields=["first_name"])

    assert User.objects.filter(producer=producer).count() == 1


def test_create_producer_account_automatically_is_a_no_op_without_email():
    producer = ProducerFactory()

    create_producer_account_automatically(producer)

    assert not User.objects.filter(producer=producer).exists()
