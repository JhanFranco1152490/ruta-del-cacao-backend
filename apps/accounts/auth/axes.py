from django.utils.crypto import salted_hmac

LOCKOUT_KEY_SALT = "apps.accounts.axes.lockout_identifier"


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
