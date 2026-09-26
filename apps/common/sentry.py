import logging

import sentry_sdk
from sentry_sdk.integrations.logging import ignore_logger

# Lista de permitidos: lo que no está aquí no sale. Una lista de bloqueo deja pasar cualquier
# campo nuevo que el SDK o un proxy agreguen (una IP en `Forwarded`, un token en `X-Csrftoken`, la
# query de la página en `Referer`), y en este sistema esos campos pueden llevar datos personales.
ALLOWED_EVENT_KEYS = frozenset(
    {
        "type",
        "event_id",
        "timestamp",
        "start_timestamp",
        "platform",
        "level",
        "logger",
        "environment",
        "release",
        "server_name",
        "sdk",
        "transaction",
        "transaction_info",
        "contexts",
        "request",
        "exception",
        "logentry",
    }
)
# El contexto de traza se descarta: el SDK continúa el trace_id y el parent_span_id que manda el
# cliente en `sentry-trace`, valores que el cliente controla.
ALLOWED_CONTEXTS = frozenset({"runtime"})
ALLOWED_REQUEST_KEYS = frozenset({"url", "method", "headers"})
ALLOWED_HEADERS = frozenset(
    {"host", "user-agent", "accept", "origin", "content-type", "content-length"}
)
APP_LOGGER_PREFIX = "apps."

logger = logging.getLogger(__name__)


def _scrub_request(request):
    scrubbed = {k: v for k, v in request.items() if k in ALLOWED_REQUEST_KEYS}
    if "url" in scrubbed:
        scrubbed["url"] = scrubbed["url"].split("?", 1)[0].split("#", 1)[0]
    if "headers" in scrubbed:
        scrubbed["headers"] = {
            k: v for k, v in scrubbed["headers"].items() if k.lower() in ALLOWED_HEADERS
        }
    return scrubbed


def _scrub_contexts(contexts):
    return {k: v for k, v in contexts.items() if k in ALLOWED_CONTEXTS}


def _scrub_exception(exception):
    # str(exc) puede traer el valor que violó una restricción (un documento, un correo). El tipo y
    # el traceback bastan para agrupar y diagnosticar.
    return {"values": [{**value, "value": ""} for value in exception["values"]]}


def _scrub(event):
    scrubbed = {k: v for k, v in event.items() if k in ALLOWED_EVENT_KEYS}
    if "request" in scrubbed:
        scrubbed["request"] = _scrub_request(scrubbed["request"])
    if "contexts" in scrubbed:
        scrubbed["contexts"] = _scrub_contexts(scrubbed["contexts"])
    if "exception" in scrubbed:
        scrubbed["exception"] = _scrub_exception(scrubbed["exception"])
    # Solo los mensajes de la app están escritos para no llevar datos; los de Django, gunicorn
    # o las librerías incluyen `str(exc)` o la URI completa con su query.
    if not str(scrubbed.get("logger") or "").startswith(APP_LOGGER_PREFIX):
        scrubbed.pop("logentry", None)
    return scrubbed


def scrub_event(event, hint):
    """Deja pasar solo campos conocidos; ante una forma inesperada descarta el evento.

    Sirve igual para errores y transacciones. Devolver `None` hace que el SDK no envíe nada.
    """
    try:
        return _scrub(event)
    except Exception:
        # Sin exc_info ni el evento: el error mismo podría traer el dato que se quería ocultar.
        logger.warning("Evento de Sentry descartado: forma inesperada")
        return None


def init_sentry(dsn, environment, transport=None):
    # Un solo lugar para las opciones de privacidad: la configuración y las pruebas usan esta
    # función, así quitar una opción rompe una prueba.
    ignore_logger("django.security.DisallowedHost")
    sentry_sdk.init(
        dsn=dsn,
        transport=transport,
        environment=environment,
        before_send=scrub_event,
        before_send_transaction=scrub_event,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        # Los breadcrumbs traen mensajes de log y URLs de terceros; no se envía ninguno. Sin
        # traces_sample_rate el tracing queda apagado: con cualquier valor un encabezado
        # `sentry-trace` entrante puede forzar transacciones.
        max_breadcrumbs=0,
        # Las métricas no pasan por before_send. Con trace_propagation_targets vacío las llamadas
        # salientes (el proveedor de correo) no llevan `sentry-trace` ni `baggage`, que traen la
        # llave pública y los valores `sentry-*` que mande el cliente.
        enable_metrics=False,
        trace_propagation_targets=[],
    )
