# Ruta del Cacao — Backend

Sistema de trazabilidad de la producción de cacao en Norte de Santander (proyecto
académico UFPS). Este repo es la API **Django** — un repo hermano de
`ruta-del-cacao-frontend` (Next.js). Vive normalmente junto al repo paraguas
`ruta-del-cacao` (workspace: `docs/`, `specs/`, contexto completo del dominio) — pero
**este archivo no depende de que ese repo exista al lado**: quien clone solo este repo debe
poder trabajar seguro con lo que sigue.

## No negociables del proyecto (resumen — la versión completa con el porqué de cada uno
vive en `AGENTS.md` del workspace, si lo tienes al lado)

- **Commits y push: los hace la persona, nunca el agente**, salvo que se pida explícito en
  esa sesión. El agente siempre propone el mensaje de commit.
- **Dos ramas fijas `main`/`dev`.** Ramas de trabajo salen de `dev`, nunca de `main`;
  integran a `dev` por PR con **squash merge**. Nadie hace force-push a ninguna de las dos.
- **Idioma:** nombres en el código (modelos, campos, funciones, endpoints) en **inglés**;
  **comentarios de código en español, sin emojis**; mensajes de commit en **inglés**,
  formato Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`),
  resumen conciso ≤ 72 caracteres. El cuerpo del commit **solo** para el porqué que el diff
  no muestra por sí solo — nunca para narrar el qué; si no hay nada así, sin cuerpo.
- **Comentarios de código nunca mencionan specs, el repo workspace, ni rutas como
  `specs/003`** — este repo puede vivir clonado solo, sin el workspace al lado, así que esa
  referencia sería un enlace roto. Si hace falta el porqué de una decisión, se escribe
  completo en el comentario mismo.
- **Los comentarios tampoco nombran el proveedor/herramienta de turno** (Railway, Vercel,
  etc.) salvo que el código dependa de un detalle propio de ese proveedor. El mecanismo real
  (variables de entorno, convención 12-factor) es el mismo sin importar el proveedor, y
  nombrarlo de más ata el comentario a una decisión de infraestructura que puede cambiar.
  Un ejemplo con nombre de proveedor sí es válido en `.env.example`, nunca en código.
- **Toda feature con código lleva tests.** Lint/formato limpio antes de commitear.
- **Nunca commitear secretos** (`.env`, `SECRET_KEY`, credenciales de base de datos).
- **Seguridad y datos: activa desde el día uno.** Este sistema maneja datos personales
  reales de productores/usuarios y autenticación real (contraseñas con hash seguro,
  autorización por roles) desde el primer sprint — no es una regla para más adelante.

## Específico de este repo — dos cosas urgentes antes de seguir

- **Modelo de usuario personalizado, antes de la primera migración real.** El proyecto
  necesita roles/permisos y campos propios de productor sobre `Usuario` — cambiar el
  modelo de auth **después** de correr migraciones reales es muy doloroso en Django. Si
  `db.sqlite3` en este repo ya tiene migraciones de `auth.User` aplicadas, este es el
  momento de resolverlo (un `AUTH_USER_MODEL` custom desde ya, o borrar y volver a migrar
  limpio), no después de que exista más código encima.
- **Base de datos: hoy es SQLite (`db.sqlite3`, el default de `startproject`), el stack
  decidido es PostgreSQL.** Configurar Postgres antes de escribir los primeros modelos
  reales, no migrar de SQLite a Postgres con datos ya cargados.

## Pendiente antes de escribir los modelos del dominio

Hay preguntas de modelo de datos sin resolver con el equipo (clasificación Premium/
Corriente/Pasilla vs. G1/G2, cardinalidad Lote↔Cosecha, integridad de la tabla
`Evidencia`, campo `municipio` en `Finca`, cardinalidad Usuario↔Rol) — están en
`docs/CONTEXTO.md` del workspace si lo tienes al lado. No escribir las migraciones
definitivas de esas tablas hasta cerrarlas.

## Stack

Django 6.1 (aún sin apps propias, sin Django REST Framework — se añade cuando arranque el
trabajo de API, por RNF-16 de interoperabilidad). Proyecto base: `config/`.
