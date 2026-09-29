import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def build_user(identity_document, **extra):
    return User(
        email="modelo@example.com",
        document_type="NIT",
        identity_document=identity_document,
        **extra,
    )


def test_full_clean_strips_separators_from_the_document():
    user = build_user("900.123.456-7")

    user.full_clean(exclude=["password"])

    assert user.identity_document == "9001234567"


@pytest.mark.parametrize("value", ["12A45", "1" * 16, "١٢٣٤٥٦"])
def test_full_clean_rejects_invalid_documents_on_the_document_field(value):
    with pytest.raises(ValidationError) as error:
        build_user(value).full_clean(exclude=["password"])

    assert "identity_document" in error.value.message_dict


def test_create_user_rejects_an_invalid_document():
    with pytest.raises(ValidationError):
        User.objects.create_user(
            email="invalido@example.com", document_type="CC", identity_document="12A45"
        )


def test_create_user_stores_the_document_without_separators():
    user = User.objects.create_user(
        email="separadores@example.com", document_type="CC", identity_document="1.090-123 456"
    )

    assert user.identity_document == "1090123456"
