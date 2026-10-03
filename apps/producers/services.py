from django.db import IntegrityError, connection, transaction
from django.db.models import Prefetch

from apps.common.producer_dependents import registered_dependents

from .exceptions import DuplicateDocument, ProducerHasRecords, ProducerNotFound, StaleVersion
from .models import DOCUMENT_UNIQUE_CONSTRAINT, PRODUCER_ROLE_CODE, Producer, ProducerAuditEvent

MEMBER_CODE_PREFIX = "PROD-"
# La secuencia tiene MAXVALUE 999999: si se agota, PostgreSQL falla y la API responde 500.
MEMBER_CODE_SEQUENCE = "producers_member_code_sequence"

# Campos del expediente que se copian a la cuenta Productor cuando cambian (HU-03): el
# documento y los nombres, nunca el contacto (correo y teléfono son propios de la cuenta).
PRODUCER_MIRRORED_FIELDS = ("document_type", "identity_document", "first_name", "last_name")
# Nombre que accounts/models.py declara para la unicidad de documento de cuentas; esta app no
# la importa (no importa de otra), así que se repite aquí, igual que PRODUCER_ROLE_CODE.
ACCOUNT_DOCUMENT_UNIQUE_CONSTRAINT = "accounts_user_document_type_number_unique"


def _account_model():
    return Producer._meta.get_field("accounts").related_model


def next_member_code() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [MEMBER_CODE_SEQUENCE])
        (value,) = cursor.fetchone()
    return f"{MEMBER_CODE_PREFIX}{value:06d}"


def get_producer(producer_id) -> Producer:
    try:
        return (
            Producer.objects.select_related("association_access")
            .prefetch_related(
                Prefetch(
                    "accounts",
                    queryset=_account_model().objects.filter(
                        groups__role__code=PRODUCER_ROLE_CODE
                    ),
                    to_attr="_producer_account",
                )
            )
            .get(pk=producer_id)
        )
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
    _sync_linked_account(producer, changed)
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


@transaction.atomic
def delete_producer(actor, producer_id, expected_version: int) -> None:
    """Elimina un productor creado por error. Solo si nada de lo que depende de él es importante;
    si lo es, no se borra nada y se ofrece desactivarlo. Deja un rastro mínimo."""
    producer = _lock_at_version(producer_id, expected_version)
    dependents = registered_dependents()
    # Se revisan todos antes de borrar nada: uno importante basta para no tocar ninguno.
    for dependent in dependents:
        reason = dependent.important_record(producer)
        if reason:
            raise ProducerHasRecords(reason)
    counts = {dependent.name: dependent.count(producer) for dependent in dependents}
    for dependent in dependents:
        dependent.delete_all(producer, actor)
    ProducerAuditEvent.objects.create(
        member_code=producer.member_code,
        producer_name=f"{producer.first_name} {producer.last_name}",
        actor=actor,
        action=ProducerAuditEvent.Action.DELETED,
        farms_deleted=counts.get("farms", 0),
        accounts_deleted=counts.get("accounts", 0),
    )
    producer.delete()


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


def _sync_linked_account(producer: Producer, changed_fields: list[str]) -> None:
    mirrored = [field for field in changed_fields if field in PRODUCER_MIRRORED_FIELDS]
    if not mirrored:
        return
    account = (
        _account_model()
        .objects.select_for_update()
        .filter(producer_id=producer.pk, groups__role__code=PRODUCER_ROLE_CODE)
        .first()
    )
    if account is None:
        # HU-02 sin cuenta vinculada todavía: nada que sincronizar.
        return
    for field in mirrored:
        setattr(account, field, getattr(producer, field))
    try:
        with transaction.atomic():
            account.save(update_fields=mirrored)
    except IntegrityError as error:
        diagnostics = getattr(error.__cause__, "diag", None)
        if getattr(diagnostics, "constraint_name", None) != ACCOUNT_DOCUMENT_UNIQUE_CONSTRAINT:
            raise
        # Sin existing_producer_id: el choque es con el documento de una cuenta, no con el de
        # otro productor, y quien edita el expediente no tiene por qué ver esa cuenta.
        raise DuplicateDocument() from None
