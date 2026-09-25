from django.db import IntegrityError, connection, transaction

from .exceptions import DuplicateDocument, ProducerNotFound, StaleVersion
from .models import DOCUMENT_UNIQUE_CONSTRAINT, Producer

MEMBER_CODE_PREFIX = "PROD-"
# La secuencia tiene MAXVALUE 999999: si se agota, PostgreSQL falla y la API responde 500.
MEMBER_CODE_SEQUENCE = "producers_member_code_sequence"


def next_member_code() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [MEMBER_CODE_SEQUENCE])
        (value,) = cursor.fetchone()
    return f"{MEMBER_CODE_PREFIX}{value:06d}"


def get_producer(producer_id) -> Producer:
    try:
        return Producer.objects.get(pk=producer_id)
    except Producer.DoesNotExist:
        raise ProducerNotFound() from None


@transaction.atomic
def create_producer(data: dict) -> Producer:
    producer = Producer(member_code=next_member_code(), **data)
    producer.full_clean(validate_unique=False, validate_constraints=False)
    _save_or_raise_duplicate(producer)
    return producer


@transaction.atomic
def update_producer(producer_id, expected_version: int, data: dict) -> Producer:
    producer = _lock_at_version(producer_id, expected_version)
    changed = [name for name, value in data.items() if getattr(producer, name) != value]
    if not changed:
        return producer
    for name in changed:
        setattr(producer, name, data[name])
    producer.full_clean(validate_unique=False, validate_constraints=False)
    producer.version += 1
    _save_or_raise_duplicate(producer, update_fields=[*changed, "version", "updated_at"])
    return producer


@transaction.atomic
def change_producer_status(producer_id, expected_version: int, status: str) -> Producer:
    producer = _lock_at_version(producer_id, expected_version)
    if producer.status == status:
        return producer
    producer.status = status
    producer.version += 1
    producer.save(update_fields=["status", "version", "updated_at"])
    return producer


def _lock_at_version(producer_id, expected_version: int) -> Producer:
    try:
        producer = Producer.objects.select_for_update().get(pk=producer_id)
    except Producer.DoesNotExist:
        raise ProducerNotFound() from None
    if producer.version != expected_version:
        raise StaleVersion()
    return producer


def _save_or_raise_duplicate(producer: Producer, **save_kwargs) -> None:
    # El duplicado lo detecta la restricción única de la base de datos: es lo único que
    # resiste dos altas simultáneas. El savepoint deja la transacción usable para buscar
    # el expediente que ya tenía el documento.
    try:
        with transaction.atomic():
            producer.save(**save_kwargs)
    except IntegrityError as error:
        # Otra restricción (el código de asociado, un NOT NULL) es un error de programa y
        # no un documento repetido: se deja subir para no ocultarlo tras un 409 engañoso.
        if not _violates_document_constraint(error):
            raise
        existing_id = (
            Producer.objects.filter(
                document_type=producer.document_type,
                identity_document=producer.identity_document,
            )
            .exclude(pk=producer.pk)
            .values_list("id", flat=True)
            .first()
        )
        raise DuplicateDocument(existing_id) from None


def _violates_document_constraint(error: IntegrityError) -> bool:
    diagnostics = getattr(error.__cause__, "diag", None)
    return getattr(diagnostics, "constraint_name", None) == DOCUMENT_UNIQUE_CONSTRAINT
