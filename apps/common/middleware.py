from django.utils.cache import add_never_cache_headers

from .paths import is_api_request


class ApiNoStoreMiddleware:
    """Marca como no almacenables todas las respuestas del API.

    Casi todas traen datos personales de productores o usuarios, así que ni el navegador ni
    un proxy intermedio deben guardar copia.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if is_api_request(request):
            add_never_cache_headers(response)
        return response
