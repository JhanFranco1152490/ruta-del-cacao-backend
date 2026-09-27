import hashlib
from collections.abc import Mapping

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle

from .axes import client_ip


class ClientIPThrottle(AnonRateThrottle):
    # La misma IP que usa axes para el bloqueo, ya validada y sin el puerto que algunos proxies
    # agregan (con el puerto, cada conexión abriría un cupo nuevo).
    def get_ident(self, request):
        return client_ip(request)


class LoginRateThrottle(ClientIPThrottle):
    scope = "login"


class PasswordResetIPThrottle(ClientIPThrottle):
    scope = "password_reset"


class PasswordResetConfirmThrottle(ClientIPThrottle):
    scope = "password_reset_confirm"


class ActivationConfirmThrottle(ClientIPThrottle):
    scope = "activation_confirm"


class PasswordResetIdentifierThrottle(SimpleRateThrottle):
    scope = "password_reset_identifier"

    def get_cache_key(self, request, view):
        # DRF consulta todos los límites aunque uno ya haya negado la petición, así que un cuerpo
        # JSON que no es un objeto llega aquí; el serializer lo rechaza después con un 400.
        data = request.data if isinstance(request.data, Mapping) else {}
        email = str(data.get("email", "")).strip().lower()
        if not email:
            return None
        digest = hashlib.sha256(email.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}
