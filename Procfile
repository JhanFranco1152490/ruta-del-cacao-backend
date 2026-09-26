# Railway no tiene una fase `release` separada (a diferencia de Heroku): todo lo que
# necesite correr antes de servir tráfico va encadenado en la misma línea `web`.
# flushexpiredtokens purga de la lista de bloqueo los tokens de renovación ya vencidos; va
# tras migrate porque necesita sus tablas.
web: python manage.py migrate --noinput && python manage.py flushexpiredtokens && python manage.py collectstatic --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT
