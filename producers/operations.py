from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .exceptions import DuplicateDocumentError, ProducerValidationError
from .models import Producer
from .services import next_member_code


@transaction.atomic
def create_producer(data):
    producer = Producer(member_code=next_member_code(), **data)
    try:
        producer.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError as error:
        raise ProducerValidationError(error.message_dict) from error

    try:
        producer.save()
    except IntegrityError as error:
        raise DuplicateDocumentError("El documento ya se encuentra registrado.") from error

    return producer
