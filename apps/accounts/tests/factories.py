import uuid

import factory
from django.contrib.auth.models import Group, Permission
from factory.django import DjangoModelFactory

from apps.accounts.models import Role, User
from apps.common.choices import DocumentType
from apps.producers.tests.factories import ProducerFactory

DEFAULT_PASSWORD = "frase segura de cacao 2026"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"persona{n}@example.com")
    document_type = DocumentType.CC
    identity_document = factory.Sequence(lambda n: str(10_000_000 + n))
    password = factory.django.Password(DEFAULT_PASSWORD)

    @factory.post_generation
    def permissions(user, create, extracted, **kwargs):
        """Recibe permisos como "app_label.codename", igual que user.has_perm()."""
        if not create or not extracted:
            return
        for permission in extracted:
            app_label, codename = permission.split(".")
            user.user_permissions.add(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )


def make_pending_user(**kwargs) -> User:
    """Cuenta recién creada por HU-03: activa, pero sin contraseña utilizable todavía."""
    user = UserFactory(**kwargs)
    user.set_unusable_password()
    user.save(update_fields=["password"])
    return user


class RoleFactory(DjangoModelFactory):
    class Meta:
        model = Role
        skip_postgeneration_save = True

    kind = Role.Kind.CUSTOM
    name = factory.Sequence(lambda n: f"Rol {n}")
    producer = factory.SubFactory(ProducerFactory)

    @factory.lazy_attribute
    def group(self):
        return Group.objects.create(name=f"role-{uuid.uuid4()}")

    @factory.post_generation
    def permissions(role, create, extracted, **kwargs):
        """Recibe permisos como "app_label.codename", igual que UserFactory."""
        if not create or not extracted:
            return
        for permission in extracted:
            app_label, codename = permission.split(".")
            role.group.permissions.add(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )


class FixedRoleFactory(RoleFactory):
    kind = Role.Kind.FIXED
    producer = None
    code = factory.Sequence(lambda n: f"fixed-{n}")


class PredefinedRoleFactory(RoleFactory):
    kind = Role.Kind.PREDEFINED
    producer = None
    code = factory.Sequence(lambda n: f"predefined-{n}")
