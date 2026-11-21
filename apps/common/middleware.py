from django.utils.cache import add_never_cache_headers

from .paths import is_api_request, is_public_api_request


class ApiNoStoreMiddleware:
    """Marca como no almacenables todas las respuestas del API.

    Casi todas traen datos personales de productores o usuarios, así que ni el navegador ni
    un proxy intermedio deben guardar copia. La excepción es lo público (`/api/public/`), que no
    los trae: ahí se respeta la caché que la vista eligió, y si no eligió ninguna, tampoco se
    guarda.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not is_api_request(request):
            return response
        if is_public_api_request(request) and response.has_header("Cache-Control"):
            return response
        add_never_cache_headers(response)
        return response
