from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import Producer


class ProducerNotFoundError(LookupError):
    pass


class StaleVersionError(ValueError):
    pass


class DuplicateDocumentError(ValueError):
    pass


@transaction.atomic
def update_producer(producer_id, expected_version, data):
    try:
        producer = Producer.objects.select_for_update().get(pk=producer_id)
    except Producer.DoesNotExist as error:
        raise ProducerNotFoundError("El productor no existe.") from error

    if producer.version != expected_version:
        raise StaleVersionError("La ficha fue modificada. Recarga antes de guardar.")

    changed_fields = []
    for field_name, value in data.items():
        if getattr(producer, field_name) != value:
            setattr(producer, field_name, value)
            changed_fields.append(field_name)

    if not changed_fields:
        return producer

    try:
        producer.full_clean()
    except ValidationError as error:
        raise DuplicateDocumentError("El documento ya se encuentra registrado.") from error
    producer.version += 1
    changed_fields.extend(["version", "updated_at"])

    try:
        producer.save(update_fields=changed_fields)
    except IntegrityError as error:
        raise DuplicateDocumentError("El documento ya se encuentra registrado.") from error

    return producer
