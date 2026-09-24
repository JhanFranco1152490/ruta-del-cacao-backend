from django.db import transaction

from .models import Producer
from .updates import ProducerNotFoundError, StaleVersionError


def _change_producer_status(producer_id, expected_version, target_status):
    try:
        producer = Producer.objects.select_for_update().get(pk=producer_id)
    except Producer.DoesNotExist as error:
        raise ProducerNotFoundError("El productor no existe.") from error

    if producer.version != expected_version:
        raise StaleVersionError("La ficha fue modificada. Recarga antes de guardar.")

    if producer.status == target_status:
        return producer

    producer.status = target_status
    producer.version += 1
    producer.save(update_fields=["status", "version", "updated_at"])
    return producer


@transaction.atomic
def deactivate_producer(producer_id, expected_version):
    return _change_producer_status(producer_id, expected_version, Producer.Status.INACTIVE)


@transaction.atomic
def activate_producer(producer_id, expected_version):
    return _change_producer_status(producer_id, expected_version, Producer.Status.ACTIVE)
