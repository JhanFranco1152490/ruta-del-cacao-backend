"""Lo que una app ofrece a las demás sin que se importen entre sí.

Cada módulo es un contrato: un registro donde la app dueña anota lo suyo al arrancar (qué depende
de una finca y cómo se elimina con ella, qué agrega al detalle de una actividad) o una regla que
varias comparten (quién responde por una labor, a quién le llegan las alertas). La
infraestructura común (bloqueos, paginación, errores, almacenamiento) queda en `apps.common`.
"""
