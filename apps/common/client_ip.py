"""La IP del cliente, la misma para todos los que la necesitan: el bloqueo de intentos de acceso y
los límites de solicitudes."""

import ipaddress
import logging

from rest_framework.throttling import AnonRateThrottle, BaseThrottle

logger = logging.getLogger(__name__)


def client_ip(request):
    """IP del cliente según DRF, para que axes y los límites de solicitudes vean la misma."""
    candidate = _without_port(BaseThrottle().get_ident(request) or "")
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        # Un salto de confianza vacío o que no es una IP (proxy mal configurado, o la app
        # alcanzable sin él): axes guarda la IP en una columna inet y fallaría con 500, y una IP
        # vacía abre un contador nuevo en cada intento, así que el bloqueo nunca llegaría. El
        # valor lo puede escribir el cliente, por eso no va en el aviso.
        logger.warning("La IP del cliente no es válida; se usa REMOTE_ADDR.")
        return request.META.get("REMOTE_ADDR")


def _without_port(value):
    # Algunos proxies escriben "ip:puerto" o "[ipv6]:puerto"; una IPv6 sola tiene varios ":".
    if value.startswith("["):
        return value[1:].partition("]")[0]
    if value.count(":") == 1:
        return value.partition(":")[0]
    return value


class ClientIPThrottle(AnonRateThrottle):
    # La misma IP que usa el bloqueo de intentos de acceso, ya validada y sin el puerto que algunos
    # proxies agregan (con el puerto, cada conexión abriría un cupo nuevo).
    def get_ident(self, request):
        return client_ip(request)
