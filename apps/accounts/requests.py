import uuid


def request_id_from(request):
    try:
        return uuid.UUID(request.headers.get("X-Request-ID", ""))
    except (TypeError, ValueError):
        return uuid.uuid4()
