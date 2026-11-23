"""Las reglas del código QR de un lote: quién puede tenerlo, su token y la dirección que lleva."""

import secrets

from django.conf import settings

from .choices import LotStatus

# Clasificado o posterior: el QR muestra la calidad del lote, que antes no existe. Vender no cambia
# el estado, así que En bodega es el único posterior; Descartado nunca lo tiene.
QR_STATUSES = frozenset({LotStatus.CLASSIFIED, LotStatus.IN_WAREHOUSE})

# 12 bytes aleatorios son 16 caracteres en base64 para URL (96 bits): imposible de recorrer
# probando, y corto para que el QR impreso tenga pocos módulos y se lea en un saco.
TOKEN_BYTES = 12


def can_have_qr(status: str) -> bool:
    return status in QR_STATUSES


def new_qr_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def public_traceability_url(token: str) -> str:
    """La dirección que lleva el QR. Queda impresa en los sacos: si el dominio del frontend cambia,
    los QR ya impresos dejan de abrir salvo que el dominio anterior redirija."""
    return f"{settings.FRONTEND_URL.rstrip('/')}/trazabilidad/{token}"
