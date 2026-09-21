from django.db import IntegrityError, transaction

from .models import Producer
from .services import next_member_code


class DuplicateDocumentError(ValueError):
    pass


@transaction.atomic
def create_producer(data):
    producer = Producer(member_code=next_member_code(), **data)
    producer.full_clean()

    try:
        producer.save()
    except IntegrityError as error:
        raise DuplicateDocumentError("El documento ya se encuentra registrado.") from error

    return producer
