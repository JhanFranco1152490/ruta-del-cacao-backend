API_PREFIX = "/api/"
# Lo que se consulta sin sesión y no trae datos personales.
PUBLIC_API_PREFIX = "/api/public/"


def is_api_request(request):
    # path_info no incluye el prefijo con que se monte la app (SCRIPT_NAME), y "/api" sin barra
    # final también es del API.
    path = request.path_info
    return path.startswith(API_PREFIX) or path == API_PREFIX.rstrip("/")


def is_public_api_request(request):
    return request.path_info.startswith(PUBLIC_API_PREFIX)
