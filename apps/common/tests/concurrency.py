from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connection


def run_in_parallel(action, arguments):
    """Corre `action(argumento)` en un hilo por argumento, todos a la vez, y devuelve los
    resultados en orden. Solo tiene sentido con `django_db(transaction=True)`: cada hilo abre su
    propia conexión y necesita ver lo que los otros confirman."""
    barrier = Barrier(len(arguments))

    def run(argument):
        try:
            barrier.wait()
            return action(argument)
        finally:
            # Con conexiones persistentes close_old_connections() no cierra la de un hilo
            # y la base de pruebas no se puede destruir con una sesión abierta.
            connection.close()

    with ThreadPoolExecutor(max_workers=len(arguments)) as executor:
        return list(executor.map(run, arguments))
