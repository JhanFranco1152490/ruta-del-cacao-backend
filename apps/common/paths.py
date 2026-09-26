API_PREFIX = "/api/"


def is_api_request(request):
    # path_info no incluye el prefijo con que se monte la app (SCRIPT_NAME), y "/api" sin barra
    # final también es del API.
    path = request.path_info
    return path.startswith(API_PREFIX) or path == API_PREFIX.rstrip("/")
