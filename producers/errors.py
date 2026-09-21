from rest_framework.response import Response


def producer_error(code, message, fields=None, status=400, **extra):
    payload = {
        "code": code,
        "message": message,
        "fields": fields or {},
    }
    payload.update(extra)
    return Response(payload, status=status)


def validation_error(fields):
    return producer_error(
        "validation_error",
        "Los datos enviados no son validos.",
        fields=fields,
