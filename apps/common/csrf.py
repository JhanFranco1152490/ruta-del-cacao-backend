from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS

CSRF_FAILED_DETAIL = "La validación de seguridad falló. Recarga la página e inténtalo de nuevo."


def enforce_csrf(request):
    """Aplica la verificación CSRF de Django a una petición de DRF.

    DRF desactiva el middleware CSRF en sus vistas y solo lo reactiva para su autenticación
    por sesión. Aquí la sesión viaja en cookies propias, así que hay que pedirlo explícito.
    """
    check = CSRFCheck(lambda _request: None)
    check.process_request(request._request)
    if check.process_view(request._request, None, (), {}):
        raise PermissionDenied(CSRF_FAILED_DETAIL)


# Un comentario y no un docstring: el esquema OpenAPI toma el docstring del mixin como
# descripción de cada operación de las vistas que lo usan.
class CsrfProtectedMixin:
    # Exige CSRF en vistas que modifican datos sin exigir sesión (login, recuperación).

    def initial(self, request, *args, **kwargs):
        # Antes del límite de solicitudes: un POST rechazado por CSRF (típicamente desde otro
        # sitio) no debe gastar el cupo de la IP de la persona a la que se le hace la petición.
        if request.method not in SAFE_METHODS:
            enforce_csrf(request)
        super().initial(request, *args, **kwargs)
