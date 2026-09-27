import uuid

import pytest
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction

from apps.accounts.models import Role
from apps.accounts.tests.factories import FixedRoleFactory, PredefinedRoleFactory, RoleFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def make_group():
    return Group.objects.create(name=f"role-{uuid.uuid4()}")


def test_custom_role_requires_producer():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Role.objects.create(group=make_group(), kind=Role.Kind.CUSTOM, name="Sin dueño")


def test_predefined_role_rejects_producer():
    producer = ProducerFactory()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Role.objects.create(
                group=make_group(),
                kind=Role.Kind.PREDEFINED,
                code="foreman-dup",
                producer=producer,
                name="Capataz con dueño",
            )


def test_custom_role_rejects_code():
    producer = ProducerFactory()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Role.objects.create(
                group=make_group(),
                kind=Role.Kind.CUSTOM,
                code="no-debería-tener-código",
                producer=producer,
                name="Rol propio con código",
            )


def test_fixed_role_requires_code():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Role.objects.create(group=make_group(), kind=Role.Kind.FIXED, name="Sin código")


def test_system_role_names_are_unique_case_insensitively():
    FixedRoleFactory(name="Administrador")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PredefinedRoleFactory(name="administrador")


def test_custom_role_names_are_unique_within_the_same_producer():
    producer = ProducerFactory()
    RoleFactory(producer=producer, name="Capataz de confianza")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RoleFactory(producer=producer, name="capataz de confianza")


def test_custom_role_names_can_repeat_across_producers():
    # La unicidad cruzada entre roles del sistema y propios se aplica en el servicio (HU-03),
    # no en la base de datos: aquí solo se comprueba que la base no la bloquea de más.
    first = RoleFactory(name="Administrador de finca")
    second = RoleFactory(name="Administrador de finca")
    assert first.producer_id != second.producer_id
