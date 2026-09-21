from django.db import DatabaseError, connection, transaction

MEMBER_CODE_PREFIX = "PROD-"
MEMBER_CODE_LIMIT = 999999
MEMBER_CODE_SEQUENCE = "producers_member_code_sequence"


class MemberCodeExhaustedError(RuntimeError):
    pass


@transaction.atomic
def next_member_code() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(%s)", [MEMBER_CODE_SEQUENCE])
            sequence_value = cursor.fetchone()[0]
    except DatabaseError as error:
        cause = error.__cause__
        if getattr(cause, "pgcode", None) == "2200H":
            raise MemberCodeExhaustedError(
                "No quedan c?digos de productor disponibles."
            ) from error
        raise

    if sequence_value > MEMBER_CODE_LIMIT:
        raise MemberCodeExhaustedError("No quedan c?digos de productor disponibles.")

    return f"{MEMBER_CODE_PREFIX}{sequence_value:06d}"
