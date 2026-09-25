import json
import os
import subprocess
import sys
from io import BytesIO
from unittest import mock
from wsgiref.util import setup_testing_defaults

import pytest
import sentry_sdk
from django.conf import settings
from django.core import signals
from django.core.exceptions import SuspiciousOperation
from django.db import close_old_connections
from sentry_sdk.transport import Transport

from apps.common.sentry import init_sentry, scrub_event

DOC = "1098765432"
CSRF = "csrf0token0marker0abcdefghijklmnop"
JWT = "eyJhbGciOiJIUzI1NiJ9.marker.jwtsignature"
IP = "203.0.113.77"
BAGGAGE = "baggagemarker4242"
TRACE_ID = "771a43a4192642f0b136d5159a501700"
MARKERS = (DOC, CSRF, JWT, IP, BAGGAGE, TRACE_ID)
DSN = "https://public@example.invalid/1"

FULL_HEADERS = {
    "HTTP_HOST": "localhost",
    "HTTP_USER_AGENT": "probe-agent",
    "HTTP_ACCEPT": "application/json",
    "HTTP_ORIGIN": "https://front.example",
    "HTTP_REFERER": f"https://front.example/productores?search={DOC}",
    "HTTP_COOKIE": f"access_token={JWT}; refresh_token={JWT}; csrftoken={CSRF}",
    "HTTP_AUTHORIZATION": f"Bearer {JWT}",
    "HTTP_X_CSRFTOKEN": CSRF,
    "HTTP_X_FORWARDED_FOR": IP,
    "HTTP_X_REAL_IP": IP,
    "HTTP_FORWARDED": f"for={IP}",
    "HTTP_CF_CONNECTING_IP": IP,
    "HTTP_TRUE_CLIENT_IP": IP,
    "HTTP_X_ENVOY_EXTERNAL_ADDRESS": IP,
    "HTTP_BAGGAGE": f"sentry-user_id={BAGGAGE},sentry-trace_id={TRACE_ID},sentry-sampled=true",
    "HTTP_SENTRY_TRACE": f"{TRACE_ID}-b0e6d1f2a3c4d5e6-1",
}


def test_scrub_event_keeps_only_safe_request_fields():
    event = {
        "request": {
            "url": f"http://localhost/api/producers?search={DOC}#frag",
            "method": "GET",
            "query_string": f"search={DOC}",
            "cookies": {"access_token": JWT},
            "data": {"email": "x"},
            "env": {"REMOTE_ADDR": IP},
            "headers": {
                "Host": "localhost",
                "User-Agent": "probe",
                "Content-Type": "application/json",
                "Referer": f"https://f.example/?search={DOC}",
                "X-Csrftoken": CSRF,
                "Forwarded": f"for={IP}",
                "CF-Connecting-IP": IP,
            },
        }
    }

    request = scrub_event(event, {})["request"]

    assert request == {
        "url": "http://localhost/api/producers",
        "method": "GET",
        "headers": {
            "Host": "localhost",
            "User-Agent": "probe",
            "Content-Type": "application/json",
        },
    }


def test_scrub_event_blanks_every_exception_message_but_keeps_type_and_stacktrace():
    event = {
        "exception": {
            "values": [
                {
                    "type": "IntegrityError",
                    "value": f"Key (identity_document)=({DOC})",
                    "stacktrace": {"frames": []},
                },
                {"type": "UniqueViolation", "value": f"dup {DOC}"},
            ]
        }
    }

    values = scrub_event(event, {})["exception"]["values"]

    assert [v["type"] for v in values] == ["IntegrityError", "UniqueViolation"]
    assert [v["value"] for v in values] == ["", ""]
    assert values[0]["stacktrace"] == {"frames": []}
    assert DOC not in str(values)


def test_scrub_event_drops_extra_breadcrumbs_and_free_form_fields():
    event = {
        "level": "error",
        "extra": {
            "request": f"<WSGIRequest: GET '/api/producers?search={DOC}'>",
            "sys.argv": [DOC],
        },
        "breadcrumbs": {"values": [{"type": "log", "message": DOC}]},
        "message": DOC,
        "user": {"ip_address": IP},
        "tags": {"a": DOC},
        "spans": [{"description": f"GET /x?search={DOC}"}],
        "_meta": {"x": DOC},
    }

    scrubbed = scrub_event(event, {})

    assert scrubbed == {"level": "error"}


def test_scrub_event_keeps_the_log_message_of_the_app_only():
    app_event = {
        "logger": "apps.common.errors",
        "logentry": {"formatted": "Error no controlado: RuntimeError"},
    }
    lib_event = {
        "logger": "django.security.SuspiciousOperation",
        "logentry": {"formatted": f"doc {DOC}"},
    }
    no_logger = {"logentry": {"formatted": f"doc {DOC}"}}

    assert scrub_event(app_event, {}) == app_event
    assert "logentry" not in scrub_event(lib_event, {})
    assert "logentry" not in scrub_event(no_logger, {})


def test_scrub_event_keeps_the_safe_metadata_that_grouping_needs():
    event = {
        "event_id": "a",
        "timestamp": 1.0,
        "platform": "python",
        "level": "error",
        "environment": "production",
        "release": "abc123",
        "server_name": "host",
        "sdk": {"name": "sentry.python"},
        "transaction": "/api/producers",
        "contexts": {
            "runtime": {"name": "CPython"},
            "trace": {"trace_id": "t"},
            "app": {"x": DOC},
        },
    }

    scrubbed = scrub_event(event, {})

    assert scrubbed["contexts"] == {"runtime": {"name": "CPython"}}
    assert {k: v for k, v in scrubbed.items() if k != "contexts"} == {
        k: v for k, v in event.items() if k != "contexts"
    }


@pytest.mark.parametrize(
    "event",
    [
        {"request": "no es un dict"},
        {"request": {"headers": ["no", "es", "un", "dict"]}},
        {"exception": {"values": 5}},
        {"contexts": []},
        {"exception": {"values": ["texto"]}},
    ],
)
def test_scrub_event_drops_the_event_when_its_shape_is_unexpected(event):
    assert scrub_event(event, {}) is None


@pytest.mark.parametrize(
    "event", [{}, {"level": "error"}, {"request": {}}, {"request": {"method": "GET"}}]
)
def test_scrub_event_tolerates_events_without_those_fields(event):
    assert scrub_event(event, {}) == event


class MemoryTransport(Transport):
    items = []

    def capture_envelope(self, envelope):
        # Las cabeceras del sobre también salen (aquí viaja el contexto de traza).
        self.items.append(envelope.headers)
        for item in envelope.items:
            self.items.append(json.loads(item.payload.get_bytes()))


@pytest.fixture
def sentry_items():
    previous = sentry_sdk.get_global_scope().client
    MemoryTransport.items = []
    init_sentry(DSN, "test", transport=MemoryTransport)
    yield MemoryTransport.items
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(previous)


@pytest.fixture
def keep_connections_open():
    # Lo mismo que hace el cliente de pruebas de Django: sin esto, cada petición revisa (y
    # puede cerrar) la conexión que la prueba tiene abierta.
    signals.request_started.disconnect(close_old_connections)
    signals.request_finished.disconnect(close_old_connections)
    yield
    signals.request_started.connect(close_old_connections)
    signals.request_finished.connect(close_old_connections)


def call_app(path, query="", extra_environ=None):
    # Se llama a la aplicación WSGI real: el cliente de pruebas de Django no pasa por el
    # envoltorio de Sentry que agrega los datos de la petición al evento.
    from config.wsgi import application

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "wsgi.input": BytesIO(b""),
        # Fuera de DEBUG el redirect a HTTPS respondería 301 antes de llegar a la vista.
        "wsgi.url_scheme": "https",
        **FULL_HEADERS,
        **(extra_environ or {}),
    }
    setup_testing_defaults(environ)
    statuses = []
    b"".join(application(environ, lambda status, headers, exc=None: statuses.append(status)))
    sentry_sdk.flush()
    return statuses[0]


def assert_no_marker_left(items):
    serialized = json.dumps(items)
    for marker in MARKERS:
        assert marker not in serialized, marker


def error_events(items):
    return [i for i in items if "exception" in i or "logentry" in i]


def test_an_exception_message_never_reaches_sentry(sentry_items, keep_connections_open):
    # Fuera de la API el manejador de errores de DRF no interviene y Django reenvía la
    # excepción con su mensaje, que puede traer el valor que violó una restricción.
    error = RuntimeError(f"Key (identity_document)=({DOC}) already exists.")
    target = "django.contrib.auth.middleware.AuthenticationMiddleware.process_request"

    with mock.patch(target, side_effect=error):
        status = call_app("/api/producers", f"search={DOC}")

    assert status.startswith("500")
    events = [e for e in error_events(sentry_items) if "exception" in e]
    assert len(events) == 1
    assert events[0]["exception"]["values"][0]["type"] == "RuntimeError"
    assert_no_marker_left(sentry_items)


def test_a_django_security_log_never_sends_the_query(sentry_items, keep_connections_open):
    target = "django.contrib.auth.middleware.AuthenticationMiddleware.process_request"

    with mock.patch(target, side_effect=SuspiciousOperation(f"documento {DOC}")):
        status = call_app("/api/producers", f"search={DOC}")

    assert status.startswith("400")
    assert error_events(sentry_items)
    assert_no_marker_left(sentry_items)


def test_a_disallowed_host_with_a_search_never_reaches_sentry(sentry_items, keep_connections_open):
    status = call_app("/api/producers", f"search={DOC}", {"HTTP_HOST": "evil.example"})

    assert status.startswith("400")
    assert error_events(sentry_items) == []
    assert_no_marker_left(sentry_items)


def test_a_500_sends_no_query_no_credentials_and_no_client_ip(sentry_items, keep_connections_open):
    with mock.patch("apps.accounts.views.get_token", side_effect=RuntimeError("boom")):
        status = call_app("/api/auth/csrf", f"search={DOC}")

    assert status.startswith("500")
    events = [e for e in error_events(sentry_items) if "request" in e]
    assert events
    request = events[0]["request"]
    assert request["url"] == "https://localhost/api/auth/csrf"
    assert {k.lower() for k in request["headers"]} <= {
        "host",
        "user-agent",
        "accept",
        "origin",
        "content-type",
        "content-length",
    }
    assert_no_marker_left(sentry_items)


def test_an_incoming_trace_header_never_creates_a_transaction(sentry_items, keep_connections_open):
    trace = "771a43a4192642f0b136d5159a501700-b0e6d1f2a3c4d5e6-1"

    status = call_app("/api/auth/csrf", f"search={DOC}", {"HTTP_SENTRY_TRACE": trace})

    assert status.startswith("200")
    assert not [i for i in sentry_items if i.get("type") == "transaction"]
    assert_no_marker_left(sentry_items)


def test_a_transaction_is_scrubbed_like_an_error():
    transaction = {
        "type": "transaction",
        "transaction": "/api/auth/csrf",
        "request": {"url": f"http://localhost/x?search={DOC}", "headers": {"Referer": DOC}},
        "spans": [{"description": f"GET /x?search={DOC}"}],
    }

    scrubbed = scrub_event(transaction, {})

    assert DOC not in str(scrubbed)
    assert scrubbed["type"] == "transaction"


def test_the_sdk_drops_an_event_when_the_scrubber_fails(sentry_items):
    sentry_sdk.capture_event({"message": DOC, "request": "no es un dict"})
    sentry_sdk.flush()

    assert sentry_items == []


def run_settings(code, **env):
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=settings.BASE_DIR,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


PRIVACY_OPTIONS = (
    "import django; django.setup(); import sentry_sdk, json; o = sentry_sdk.get_client().options; "
    "print(json.dumps({'pii': o['send_default_pii'], 'body': o['max_request_body_size'], "
    "'locals': o['include_local_variables'], 'traces': o['traces_sample_rate'], "
    "'crumbs': o['max_breadcrumbs'], 'metrics': o['enable_metrics'], "
    "'targets': o['trace_propagation_targets'], "
    "'send': o['before_send'].__name__, 'send_tx': o['before_send_transaction'].__name__, "
    "'env': o['environment']}))"
)


def test_settings_init_sentry_with_every_privacy_option():
    options = json.loads(run_settings(PRIVACY_OPTIONS, SENTRY_DSN=DSN, DEBUG="False"))

    assert options == {
        "pii": False,
        "body": "never",
        "locals": False,
        "traces": None,
        "crumbs": 0,
        "metrics": False,
        "targets": [],
        "send": "scrub_event",
        "send_tx": "scrub_event",
        "env": "production",
    }


def test_the_environment_defaults_to_development_when_debug_is_on():
    options = json.loads(run_settings(PRIVACY_OPTIONS, SENTRY_DSN=DSN, DEBUG="True"))

    assert options["env"] == "development"


def test_sentry_stays_off_without_a_dsn():
    code = (
        "import django, sys; django.setup(); import sentry_sdk; "
        "print(sentry_sdk.get_client().is_active())"
    )

    assert run_settings(code, SENTRY_DSN="") == "False"
