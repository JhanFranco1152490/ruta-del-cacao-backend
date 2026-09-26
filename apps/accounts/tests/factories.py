import factory
from django.contrib.auth.models import Permission
from factory.django import DjangoModelFactory

from apps.accounts.models import User
from apps.common.choices import DocumentType

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
