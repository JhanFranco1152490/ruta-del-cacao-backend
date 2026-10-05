from .models import AccountManagementEvent


def record_account_event(
    event_type: str,
    request_id,
    *,
    actor=None,
    target_user=None,
    target_role_id=None,
    target_user_ref=None,
) -> None:
    AccountManagementEvent.objects.create(
        event_type=event_type,
        actor=actor,
        target_user=target_user,
        target_role_id=target_role_id,
        target_user_ref=target_user_ref,
        request_id=request_id,
    )
