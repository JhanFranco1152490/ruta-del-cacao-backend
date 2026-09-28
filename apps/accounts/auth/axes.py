import ipaddress
import logging

from django.utils.crypto import salted_hmac
from rest_framework.throttling import BaseThrottle

logger = logging.getLogger(__name__)

LOCKOUT_KEY_SALT = "apps.accounts.axes.lockout_identifier"


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


def lockout_identifier(request, credentials):
    """Identificador con el que axes cuenta los intentos: un hash con llave, nunca el correo.

    Con la llave, un volcado de la tabla de axes no se revierte probando correos o números de
    documento. Rotar SECRET_KEY solo descarta contadores de 15 minutos.
    """
    username = (credentials or {}).get("username")
    if not username:
        return None
    normalized = username.strip().lower()
    # La sal separa esta llave de los demás usos de SECRET_KEY (sesiones, enlaces firmados).
    return salted_hmac(LOCKOUT_KEY_SALT, normalized, algorithm="sha256").hexdigest()
