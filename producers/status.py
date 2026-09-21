from django.db import transaction

from .models import Producer
from .updates import ProducerNotFoundError, StaleVersionError


@transaction.atomic
def deactivate_producer(producer_id, expected_version):
    try:
        producer = Producer.objects.select_for_update().get(pk=producer_id)
    except Producer.DoesNotExist as error:
        raise ProducerNotFoundError("El productor no existe.") from error

    if producer.version != expected_version:
        raise StaleVersionError("La ficha fue modificada. Recarga antes de guardar.")

    if producer.status == Producer.Status.INACTIVE:
        return producer

    producer.status = Producer.Status.INACTIVE
    producer.version += 1
    producer.save(update_fields=["status", "version", "updated_at"])
    return producer
