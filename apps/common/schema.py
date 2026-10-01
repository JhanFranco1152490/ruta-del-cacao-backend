from .serializers import ApiErrorSerializer

# drf-spectacular trata todo PATCH como una edición parcial y no marca ningún campo como
# requerido, pero estos lo son siempre: sin ellos la API responde 400.
REQUIRED_ON_PATCH = {
    "PatchedProducerUpdateRequest": ["expected_version"],
    "PatchedProducerStatusRequest": ["status", "expected_version"],
    "PatchedFarmUpdateRequest": ["expected_version"],
}


def error_responses(*codes):
    """Respuestas de error con el cuerpo estándar de la API, para `extend_schema`."""
    return {code: ApiErrorSerializer for code in codes}


def require_patch_body_fields(result, **kwargs):
    """Hook de posprocesado: marca como requeridos los campos de `REQUIRED_ON_PATCH`."""
    schemas = result["components"]["schemas"]
    for name, required in REQUIRED_ON_PATCH.items():
        if name not in schemas:
            raise ValueError(
                f"El componente {name} no está en el esquema: actualiza REQUIRED_ON_PATCH "
                "para que siga el nombre que genera drf-spectacular."
            )
        unknown = [field for field in required if field not in schemas[name]["properties"]]
        if unknown:
            raise ValueError(f"El componente {name} no tiene los campos {unknown}.")
        schemas[name]["required"] = required

    # Con campos requeridos el cuerpo también lo es: sin esto el cliente lo vería opcional.
    for operations in result["paths"].values():
        for operation in operations.values():
            for media in operation.get("requestBody", {}).get("content", {}).values():
                if media["schema"].get("$ref", "").rsplit("/", 1)[-1] in REQUIRED_ON_PATCH:
                    operation["requestBody"]["required"] = True
    return result
