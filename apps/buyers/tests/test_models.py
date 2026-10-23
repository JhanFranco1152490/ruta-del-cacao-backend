import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.buyers.models import Buyer, BuyerAuditEvent
from apps.producers.tests.factories import ProducerFactory

from .factories import BuyerFactory

pytestmark = pytest.mark.django_db


def build(**fields):
    fields.setdefault("producer", ProducerFactory())
    fields.setdefault("name", "Chocolates del Oriente S.A.S.")
    fields.setdefault("document_type", "NIT")
    fields.setdefault("identity_document", "900123456")
    fields.setdefault("buyer_type", "chocolate_industry")
    fields.setdefault("phone", "3001234567")
    return Buyer(**fields)


def clean(buyer):
    buyer.full_clean(validate_unique=False, validate_constraints=False)
    return buyer


def errors_of(buyer) -> dict:
    with pytest.raises(ValidationError) as error:
        clean(buyer)
    return error.value.message_dict


def test_the_buyer_types_are_the_five_of_the_story_in_its_order():
    assert Buyer.BuyerType.labels == [
        "Industria chocolatera",
        "Exportador",
        "Intermediario o acopiador",
        "Cooperativa o asociación",
        "Transformador artesanal",
    ]


def test_clean_trims_the_texts_and_lowers_the_email():
    buyer = clean(
        build(name="  Cacao Andino  ", contact_name="  Persona Uno ", email="Compras@Example.COM")
    )

    assert buyer.name == "Cacao Andino"
    assert buyer.contact_name == "Persona Uno"
    assert buyer.email == "compras@example.com"


def test_empty_optional_fields_are_stored_as_null():
    buyer = clean(build(contact_name="   ", email="", phone="3001234567"))

    assert buyer.contact_name is None
    assert buyer.email is None


@pytest.mark.parametrize("name", ["C", "x" * 121, "", "   "])
def test_name_outside_2_to_120_characters_is_rejected(name):
    assert "name" in errors_of(build(name=name))


@pytest.mark.parametrize("contact_name", ["P", "x" * 121])
def test_contact_name_outside_2_to_120_characters_is_rejected(contact_name):
    assert "contact_name" in errors_of(build(contact_name=contact_name))


@pytest.mark.parametrize("document", ["12345", "1" * 16, "900.123.456", "900123456-7", "NIT9001"])
def test_the_document_must_have_6_to_15_digits_only(document):
    assert "identity_document" in errors_of(build(identity_document=document))


@pytest.mark.parametrize("document", ["123456", "1" * 15, "000123456"])
def test_the_document_accepts_6_to_15_digits_and_leading_zeros(document):
    clean(build(identity_document=document))


def test_a_document_type_outside_the_options_is_rejected():
    assert "document_type" in errors_of(build(document_type="RUT"))


def test_a_buyer_type_outside_the_options_is_rejected():
    assert "buyer_type" in errors_of(build(buyer_type="retail"))


@pytest.mark.parametrize("phone", ["123456", "12345678901", "300-123-4567", "+573001234567"])
def test_the_phone_must_have_7_to_10_digits_only(phone):
    assert "phone" in errors_of(build(phone=phone))


def test_an_invalid_email_is_rejected():
    assert "email" in errors_of(build(email="compras@", phone=None))


def test_a_phone_or_an_email_is_required():
    errors = errors_of(build(phone=None, email=None))

    assert errors["phone"] == errors["email"] == ["Escribe un teléfono o un correo."]


def test_only_an_email_or_only_a_phone_is_enough():
    clean(build(phone=None, email="compras@example.com"))
    clean(build(phone="3001234567", email=None))


def test_the_database_requires_a_phone_or_an_email():
    with pytest.raises(IntegrityError), transaction.atomic():
        BuyerFactory(phone=None, email=None)


def test_the_document_is_unique_per_producer_and_type():
    first = BuyerFactory(document_type="NIT", identity_document="900123456")

    with pytest.raises(IntegrityError), transaction.atomic():
        BuyerFactory(producer=first.producer, document_type="NIT", identity_document="900123456")

    BuyerFactory(producer=first.producer, document_type="CC", identity_document="900123456")
    BuyerFactory(document_type="NIT", identity_document="900123456")


def test_the_document_stays_unique_with_the_existing_buyer_inactive():
    first = BuyerFactory(is_active=False)

    with pytest.raises(IntegrityError), transaction.atomic():
        BuyerFactory(
            producer=first.producer,
            document_type=first.document_type,
            identity_document=first.identity_document,
        )


def test_the_name_can_repeat_with_another_document():
    first = BuyerFactory(name="Cacao Andino")

    BuyerFactory(producer=first.producer, name="Cacao Andino")


def test_a_producer_with_buyers_is_protected():
    buyer = BuyerFactory()

    with pytest.raises(ProtectedError):
        buyer.producer.delete()


def test_buyers_are_ordered_by_name_without_case():
    producer = ProducerFactory()
    BuyerFactory(producer=producer, name="cacao Andino")
    BuyerFactory(producer=producer, name="Bocadillos")
    BuyerFactory(producer=producer, name="Aroma")

    names = list(Buyer.objects.filter(producer=producer).values_list("name", flat=True))

    assert names == ["Aroma", "Bocadillos", "cacao Andino"]


def test_the_audit_event_survives_the_buyer_and_keeps_no_personal_data():
    buyer = BuyerFactory(buyer_type=Buyer.BuyerType.EXPORTER)
    event = BuyerAuditEvent.record(
        buyer=buyer,
        buyer_ref=buyer.pk,
        buyer_type=buyer.buyer_type,
        actor=None,
        action=BuyerAuditEvent.Action.DELETED,
        version=buyer.version,
    )
    buyer_id = buyer.pk
    buyer.delete()
    event.refresh_from_db()

    assert event.buyer is None
    assert event.buyer_ref == buyer_id
    assert event.buyer_type == "exporter"
    stored = {field.name for field in BuyerAuditEvent._meta.get_fields()}
    assert not stored & {"name", "buyer_name", "identity_document", "phone", "email", "changes"}
