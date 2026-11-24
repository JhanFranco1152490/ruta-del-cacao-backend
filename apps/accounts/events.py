from .models import AccountManagementEvent, Role


def record_account_event(
    event_type: str,
    request_id,
    *,
    actor=None,
    target_user=None,
    target_role_id=None,
    target_user_ref=None,
    producer_ref=None,
) -> None:
    """`producer_ref` es el productor de la cuenta o del rol sobre el que se actúa: se toma de
    `target_user` o del rol. Lo pasa quien llama cuando la cuenta o el rol ya se eliminaron."""
    if producer_ref is None:
        producer_ref = _producer_of(target_user, target_role_id)
    AccountManagementEvent.objects.create(
        event_type=event_type,
        actor=actor,
        target_user=target_user,
        target_role_id=target_role_id,
        target_user_ref=target_user_ref,
        request_id=request_id,
        producer_ref=producer_ref,
    )


def _producer_of(target_user, target_role_id):
    if target_user is not None:
        return target_user.producer_id
    if target_role_id is not None:
        return Role.objects.filter(pk=target_role_id).values_list("producer_id", flat=True).first()
    return None
