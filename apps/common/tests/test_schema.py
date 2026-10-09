from importlib import import_module, reload

import pytest
import yaml
from django.core.management import call_command
from django.urls import clear_url_caches

pytestmark = pytest.mark.django_db


@pytest.fixture
def schema(tmp_path):
    path = tmp_path / "schema.yml"
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(path))
    return yaml.safe_load(path.read_text())


def test_schema_is_valid_and_documents_the_api(schema):
    assert "/api/producers" in schema["paths"]
    assert "/api/producers/{id}/status" in schema["paths"]
    assert "/api/auth/login" in schema["paths"]
    # "ProducerDetail" y no "Producer": las respuestas usan ProducerDetailSerializer desde
    # que el correo del expediente puede venir nulo (ver producers/views.py).
    for component in ("ProducerDetail", "ProducerRequest", "Session", "ApiError"):
        assert component in schema["components"]["schemas"]


def test_producer_list_documents_filters_and_pagination(schema):
    parameters = {p["name"] for p in schema["paths"]["/api/producers"]["get"]["parameters"]}

    assert {"search", "status", "municipality_code", "page", "page_size"} <= parameters


@pytest.fixture
def reload_urls(settings):
    # Las rutas del esquema se registran al importar el módulo de URLs según DEBUG, así que
    # cada prueba lo vuelve a importar con el valor que necesita.
    def _reload(debug):
        settings.DEBUG = debug
        clear_url_caches()
        reload(import_module("config.urls"))

    yield _reload
    _reload(False)


def test_schema_is_not_published_outside_debug(client, reload_urls):
    reload_urls(debug=False)

    assert client.get("/api/schema").status_code == 404
    assert client.get("/api/docs").status_code == 404


def test_schema_and_docs_are_published_in_debug(client, reload_urls):
    reload_urls(debug=True)

    assert client.get("/api/schema").status_code == 200
    assert client.get("/api/docs").status_code == 200


def test_schema_and_docs_keep_their_own_renderers_with_json_only_api(client, reload_urls):
    reload_urls(debug=True)

    docs = client.get("/api/docs", HTTP_ACCEPT="text/html")
    schema_json = client.get("/api/schema", HTTP_ACCEPT="application/json")

    assert docs.status_code == 200
    assert docs["Content-Type"].startswith("text/html")
    assert schema_json.status_code == 200
    assert schema_json["Content-Type"].startswith("application/json")
    assert "paths" in schema_json.json()


def responses_of(schema, path, method):
    return schema["paths"][path][method]["responses"]


@pytest.mark.parametrize(
    ("path", "method", "codes"),
    [
        ("/api/auth/login", "post", {"200", "400", "401", "403", "429"}),
        ("/api/auth/refresh", "post", {"204", "401", "403"}),
        ("/api/auth/logout", "post", {"204", "403"}),
        ("/api/auth/me", "get", {"200", "401"}),
        ("/api/auth/password-reset/request", "post", {"202", "400", "403", "429"}),
        ("/api/auth/password-reset/confirm", "post", {"204", "400", "403", "429"}),
        ("/api/catalogs/municipalities", "get", {"200", "401"}),
        ("/api/producers", "get", {"200", "400", "401", "403", "404"}),
        ("/api/producers", "post", {"201", "400", "401", "403", "409"}),
        ("/api/producers/{id}", "get", {"200", "401", "403", "404"}),
        ("/api/producers/{id}", "patch", {"200", "400", "401", "403", "404", "409"}),
        ("/api/producers/{id}/status", "patch", {"200", "400", "401", "403", "404", "409"}),
    ],
)
def test_each_endpoint_documents_the_responses_it_returns(schema, path, method, codes):
    assert set(responses_of(schema, path, method)) == codes


def test_only_endpoints_that_read_the_session_declare_the_cookie(schema):
    assert schema["components"]["securitySchemes"]["cookieAuth"]["name"] == "cacao_access"
    for path in ("/api/auth/login", "/api/auth/refresh", "/api/auth/logout"):
        assert schema["paths"][path]["post"]["security"] == [{}]
    assert schema["paths"]["/api/auth/me"]["get"]["security"] == [{"cookieAuth": []}]


def test_error_body_has_the_shape_the_client_reads(schema):
    error = schema["components"]["schemas"]["ApiError"]

    assert set(error["properties"]) == {"detail", "code", "fields"}
    assert set(error["required"]) == {"detail", "code", "fields"}


def test_duplicate_document_conflict_documents_the_existing_producer(schema):
    body = responses_of(schema, "/api/producers", "post")["409"]["content"]["application/json"]
    conflict = schema["components"]["schemas"][body["schema"]["$ref"].rsplit("/", 1)[-1]]

    assert "existing_producer_id" in conflict["properties"]
    assert "existing_producer_id" not in conflict["required"]


# Descripciones intencionales: las ediciones parciales, el alta de fincas (su `id` de cliente) y
# los dos endpoints del mapa de fincas (qué devuelven y con qué alcance). Las de los enums las
# arma drf-spectacular a partir de las opciones del modelo.
DOCUMENTED_OPERATIONS = {
    ("patch", "/api/producers/{id}"),
    ("post", "/api/farms"),
    ("patch", "/api/farms/{id}"),
    ("delete", "/api/farms/{id}"),
    ("get", "/api/farms/map/municipalities"),
    ("get", "/api/farms/map/points"),
    ("post", "/api/plots"),
    ("patch", "/api/plots/{id}"),
    ("delete", "/api/plots/{id}"),
    ("get", "/api/cacao-varieties"),
    ("post", "/api/cacao-varieties"),
    ("patch", "/api/cacao-varieties/{id}"),
    ("get", "/api/plot-characterizations"),
    ("get", "/api/plot-characterizations/{id}"),
    ("get", "/api/plot-characterizations/{id}/history"),
    ("put", "/api/plot-characterizations/{id}"),
    ("get", "/api/agricultural-inputs"),
    ("post", "/api/agricultural-inputs"),
    ("patch", "/api/agricultural-inputs/{id}"),
    ("delete", "/api/agricultural-inputs/{id}"),
    ("get", "/api/input-stocks"),
    ("get", "/api/input-movements"),
    ("post", "/api/input-movements"),
}


def test_components_do_not_leak_internal_docstrings(schema):
    leaked = [
        f"{method} {path}"
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
        if "description" in operation and (method, path) not in DOCUMENTED_OPERATIONS
    ]
    leaked += [
        name
        for name, component in schema["components"]["schemas"].items()
        if "description" in component and "enum" not in component
    ]

    assert leaked == []


def test_partial_update_documents_the_minimum_body(schema):
    description = schema["paths"]["/api/producers/{id}"]["patch"]["description"]

    assert "expected_version" in description


def test_patch_bodies_require_the_concurrency_fields(schema):
    components = schema["components"]["schemas"]

    assert set(components["PatchedProducerUpdateRequest"]["required"]) == {"expected_version"}
    assert set(components["PatchedProducerStatusRequest"]["required"]) == {
        "status",
        "expected_version",
    }
    for path in ("/api/producers/{id}", "/api/producers/{id}/status"):
        assert schema["paths"][path]["patch"]["requestBody"]["required"] is True


def test_schema_hook_fails_when_a_patch_component_is_missing():
    from apps.common.schema import require_patch_body_fields

    with pytest.raises(ValueError, match="PatchedProducerUpdateRequest"):
        require_patch_body_fields({"components": {"schemas": {}}, "paths": {}})


def test_producer_list_marks_every_field_as_always_present(schema):
    component = schema["components"]["schemas"]["ProducerList"]

    assert set(component["required"]) == set(component["properties"])


def test_schema_and_docs_ignore_an_invalid_session_cookie(client, settings, reload_urls):
    reload_urls(debug=True)
    client.cookies[settings.AUTH_ACCESS_COOKIE] = "not-a-token"

    assert client.get("/api/schema").status_code == 200
    assert client.get("/api/docs").status_code == 200
