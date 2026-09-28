import pytest
from django.core import mail
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.accounts.system_roles import ADMINISTRATOR
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.roles import make_administrator

pytestmark = pytest.mark.django_db

VALID_ARGS = {
    "email": "admin@example.com",
    "document_type": "CC",
    "identity_document": "10000000",
    "first_name": "Ana",
    "last_name": "Torres",
}


def call(**overrides):
    args = {**VALID_ARGS, **overrides}
    call_command(
        "create_association_admin",
        f"--email={args['email']}",
        f"--document-type={args['document_type']}",
        f"--identity-document={args['identity_document']}",
        f"--first-name={args['first_name']}",
        f"--last-name={args['last_name']}",
    )


def test_creates_the_administrator_account_with_an_unusable_password():
    call()

    user = User.objects.get(email=VALID_ARGS["email"])
    assert not user.has_usable_password()
    assert user.groups.filter(role__code=ADMINISTRATOR).exists()


def test_sends_the_activation_email():
    call()

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [VALID_ARGS["email"]]


def test_refuses_when_an_administrator_already_exists():
    make_administrator()

    with pytest.raises(CommandError):
        call(email="otro@example.com", identity_document="20000000")

    assert not User.objects.filter(email="otro@example.com").exists()


def test_a_duplicate_email_creates_nothing():
    UserFactory(email=VALID_ARGS["email"])

    with pytest.raises(CommandError):
        call()

    assert User.objects.filter(email=VALID_ARGS["email"]).count() == 1


def test_a_duplicate_document_creates_nothing():
    UserFactory(document_type="CC", identity_document=VALID_ARGS["identity_document"])

    with pytest.raises(CommandError):
        call(email="nuevo@example.com")

    assert not User.objects.filter(email="nuevo@example.com").exists()


def test_an_invalid_email_creates_nothing():
    with pytest.raises(CommandError):
        call(email="no-es-correo")

    assert not User.objects.filter(document_type="CC", identity_document="10000000").exists()
