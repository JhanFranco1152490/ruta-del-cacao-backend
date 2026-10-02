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

## Stack y estructura

Python 3.12 · Django 6.1 + Django REST Framework · PostgreSQL (psycopg 3). Sesión con
`djangorestframework-simplejwt`, bloqueo de intentos con `django-axes`, filtros con
`django-filter`, esquema OpenAPI con `drf-spectacular`, correo con `django-anymail`, estáticos
con WhiteNoise, `gunicorn` como servidor y Sentry opcional. Toda la configuración sale de
variables de entorno (`python-decouple`, ver "Variables de entorno").

| Ruta               | Qué contiene                                                                    |
| ------------------ | ------------------------------------------------------------------------------- |
| `config/`          | Ajustes, URLs raíz, WSGI/ASGI                                                   |
| `apps/common/`     | Lo transversal: `ApiError` y el manejador de errores, paginación, permisos por acción, CSRF, validadores, catálogo de municipios, middleware `no-store`, vistas 404/500 en JSON |
| `apps/accounts/`   | Usuario (se identifica por correo), sesión, recuperación de contraseña, bloqueo por intentos, eventos de autenticación |
| `apps/producers/`  | Productores: alta, consulta, edición y cambio de estado                         |
| `apps/farms/`      | Fincas: alta (también sin conexión), consulta, edición, activación y su auditoría, y los conteos y puntos del mapa por municipios. El productor y sus empleados ven las suyas; la asociación lee las de todos (`services/scope.py`) |

### Capas

`views → services → models`, en una sola dirección:

- **views** (HTTP): reciben la petición, validan con serializers, aplican permisos y arman la
  respuesta. No tienen lógica de negocio.
- **services**: reglas y transacciones (`transaction.atomic`, `select_for_update`). No arman
  respuestas HTTP; un caso de negocio fallido se lanza como `ApiError`.
- **models**: datos, restricciones y validadores.

Lo que usa una sola app vive en esa app; lo transversal, o lo que ya necesita una segunda app,
sube a `apps/common`. Ninguna app importa de otra y `common` no importa de ninguna. Un módulo
que pasa de ~250 líneas o mezcla temas se convierte en paquete (`services/__init__.py` + un
archivo por tema) sin cambiar quién lo importa.

Antes de escribir la migración de una tabla nueva del dominio (fincas, parcelas, lotes,
cosechas, evidencias…), su diseño debe estar aprobado con el equipo. Si tienes el workspace
al lado, el modelo de datos está en `specs/arquitectura/001-modelo-datos-dominio.md`.

## Contrato de la API

- **Solo JSON.** No hay API navegable ni se aceptan formularios: un cuerpo que no es JSON
  responde `415` (`unsupported_media_type`) y un `Accept` que no admite JSON, `406`
  (`not_acceptable`).
- **Rutas sin barra final:** `/api/producers`, `/api/producers/{id}`, `/api/auth/login`.
- **Todo error tiene la forma** `{"detail": str, "code": str, "fields": {campo: [str]}}`;
  `fields` es `{}` si el error no es de un campo, y algunos errores agregan claves
  documentadas (`existing_producer_id`; `current` en el `stale_version` y en el
  `farm_id_conflict` de una finca propia, con la versión del servidor). Los errores de negocio son subclases de `ApiError`
  (su `default_code` es el `code`) y el manejador global de `apps/common/exceptions.py` arma el
  cuerpo: nunca se responde `Response({...})` a mano con otra forma. Una ruta que no existe
  bajo `/api/` (404) y un fallo no controlado (500, sin datos técnicos) responden con la misma
  forma (con `DEBUG=True`, Django muestra en su lugar su página técnica de depuración).
- **Códigos:** `validation_error`, `invalid_reset_token`, `parse_error`, `location_required`
  (400); `not_authenticated`, `authentication_failed`, `invalid_credentials` (401);
  `permission_denied`, `account_inactive`, `account_locked` (403); `not_found` (404);
  `method_not_allowed` (405); `not_acceptable` (406); `duplicate_document`, `stale_version`,
  `duplicate_farm_name`, `farm_id_conflict`, `farm_has_records` (409); `payload_too_large`
  (413);
  `unsupported_media_type` (415); `invalid_coordinates`, `location_outside_operating_area`,
  `municipality_department_mismatch` (422); `throttled` (429); `internal_error` (500). El frontend decide qué hacer según `code`,
  no según `detail`.
- **Registros creados sin conexión** (hoy, fincas): el `POST` acepta un `id` UUID generado en
  el dispositivo. Reenviar el mismo `id` con el mismo contenido responde `200` con el registro
  ya creado (nunca duplica, ni con dos envíos simultáneos); con otro contenido u otro dueño,
  `409`. Si el registro es del mismo dueño, ese `409` trae el del servidor en `current`: suele
  ser un pendiente editado en el dispositivo tras una creación cuya respuesta se perdió, y el
  cliente lo envía como `PATCH` con esa `version`. Si es de otro dueño, sin `current`, para no
  revelar sus datos. El `PATCH` exige `expected_version`; si el registro ya tiene exactamente lo que se
  pide (un reintento cuya respuesta se perdió) responde `200` sin cambios, y si no, `409
  stale_version`. `captured_at` (hora del dispositivo) es opcional e informativo: el orden y
  los conflictos se deciden con `version` y con la hora del servidor.
- **Paginación única:** `page` (desde 1) y `page_size` (1–100, 20 por defecto); respuesta
  `{"count", "next", "previous", "results"}`. Una página fuera de rango responde 404
  `not_found`.
- **La búsqueda de productores ignora mayúsculas y tildes** (`perez` encuentra `Pérez`) con
  la extensión `unaccent` de PostgreSQL, que habilita una migración de `producers`: el usuario
  de la base de datos necesita permiso para crear extensiones (`unaccent` es de confianza
  desde PostgreSQL 13, no exige ser superusuario).
- **Todas las respuestas bajo `/api/` llevan `Cache-Control: no-store`** (traen datos
  personales).
- **Esquema OpenAPI** con `drf-spectacular`: `GET /api/schema` y Swagger en `/api/docs`, **solo
  con `DEBUG=True`**. Las vistas declaran sus respuestas de error con `error_responses(...)`
  (`apps/common/schema.py`) para que el esquema traiga la forma estándar. El frontend debe
  generar sus tipos con `openapi-typescript` a partir de este esquema y no escribirlos a mano:
  un endpoint o campo nuevo debe quedar reflejado en el esquema en el mismo PR.
  Se valida con `python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml`.

## Sesión, CSRF y acceso

- **La sesión va en cookies `HttpOnly`** (nunca en `localStorage` ni en un header): `cacao_access`
  (15 min, `Path=/api/`) y `cacao_refresh` (7 días, `Path=/api/auth/`), `Secure` fuera de
  desarrollo y con `SameSite` (`Lax` por defecto). Renovar rota el token de renovación y pone
  el anterior en la lista de bloqueo; cambiar la contraseña invalida los tokens de acceso ya
  emitidos. Una cookie de acceso vencida o basura da `401`, nunca `403` ni `500`.
- **CSRF en toda petición que modifica datos:** `POST`, `PUT`, `PATCH` y `DELETE` exigen el
  header `X-CSRFToken`; el token sale de `GET /api/auth/csrf`. Se aplica en un solo lugar
  (`apps/common/csrf.py`), desde `CookieJWTAuthentication` y `CsrfProtectedMixin`.
- **Permisos por acción:** la vista declara `action_permissions = {"list": "app.codename", ...}`
  y `ActionPermission` los exige; una acción sin permiso declarado se niega.
- **Todo permiso nuevo se declara en `apps/accounts/registry.py` y es delegable por defecto.**
  Si actúa sobre el espacio de un productor (sus fincas, sus cuentas, su operación), el
  productor puede dárselo a un empleado de confianza en un rol propio. Solo se marca
  `delegable=False` con la razón escrita al lado, por ejemplo que actúe sobre toda la
  asociación (`producers.*`) o que proteja la cuenta Productor
  (`accounts.association_access_manage`). Un permiso de acción declara además su dependencia de
  vista en `PERMISSION_DEPENDENCIES` (crear o editar sin poder consultar no sirve). Un código
  que no está en el registro queda no delegable, pero eso es una red contra el olvido, no la
  forma de decidirlo.
- **Intentos de acceso:** `django-axes` bloquea la pareja correo + IP tras 5 fallos durante 15
  minutos (guarda un hash con llave, nunca el correo) y DRF limita las solicitudes de login,
  de recuperación de contraseña y de confirmación del enlace. Los límites de DRF usan la caché
  local por proceso (no hay `CACHES` configurado): con varios workers no se comparten. El
  bloqueo de axes sí, porque va por base de datos.
- **Desbloquear una cuenta antes de los 15 minutos:** borrar su fila en el admin de
  `AccessAttempt` (se busca por IP) o correr `python manage.py axes_reset` (todas) o
  `axes_reset_ip <ip>`; `axes_reset_username <correo>` no sirve, porque axes guarda el hash y no
  el correo. El admin no expone los tokens de renovación: `token_blacklist` está dado de baja
  de él (`apps/accounts/admin.py`).
- **`TRUSTED_PROXY_COUNT` decide qué IP se toma como la del cliente**, y de ella dependen el
  límite de solicitudes y el bloqueo de axes: debe ser `1` si la app está detrás de un solo
  proxy que agrega `X-Forwarded-For`, y `0` si no hay proxy. Con `0` detrás de un proxy, todos
  los clientes comparten la IP del proxy y el límite de solicitudes y el bloqueo dejan de ser
  por cliente; con un valor mayor que el de proxies reales, un cliente puede inventarse su IP.

## Admin de Django

- Usuarios, roles y eventos (autenticación y de cuentas) en `apps/accounts/admin.py`;
  productores en `apps/producers/admin.py`.
- **Productores:** los permisos siguen a los de la API (`producers.view`, `producers.update`,
  `producers.change_status`), no a los que Django genera. No se puede crear ni borrar desde el
  admin (el alta asigna el código de asociado y detecta el documento repetido; al productor se
  le cambia el estado, no se le borra). Se editan nombre, teléfono, correo, municipio y fecha de
  ingreso; el documento, el código y el estado no. El estado cambia con las acciones "Activar" y
  "Desactivar".
- **`Role` reemplaza a `Group`** en el admin (HU-03): `Group` se da de baja y `Role` entra de
  solo lectura, porque crear, editar o borrar un rol pasa por sus propias invariantes
  (`role_services.py`) y el admin las saltaría. La ficha de usuario muestra el productor
  vinculado y sus roles también de solo lectura, por el mismo motivo — asignar o quitar un rol
  pasa por la API de cuentas, con sus reglas (nadie concede más de lo que tiene, siempre queda
  un administrador activo).
- **`create_association_admin`** (management command) crea la cuenta Administrador inicial de
  la asociación y le envía la activación; se niega si ya existe una. Uso:
  `python manage.py create_association_admin --email a@b.com --document-type CC
  --identity-document 1234567 --first-name Ana --last-name Gómez`.
- Todo cambio desde el admin pasa por `services` y sube `version`: la ficha lleva la versión con
  la que se abrió y, si otra persona la cambió antes, no se guarda.

## Variables de entorno

Se leen en `config/settings.py`; `.env` es local y nunca se commitea, y `.env.example` lista
las variables con valores de ejemplo.

| Variable | Para qué |
| --- | --- |
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Básicas. `DEBUG` es `True` si no se define: en despliegue va `False` |
| `DATABASE_URL` | Conexión completa en despliegue. En local se usan `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` |
| `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | Origen(es) del frontend |
| `FRONTEND_URL`, `DEFAULT_FROM_EMAIL` | Base del enlace de recuperación de contraseña y remitente |
| `AUTH_JWT_SIGNING_KEY`, `AUTH_COOKIE_SECURE`, `AUTH_COOKIE_SAMESITE` | Sesión. La llave por defecto es `SECRET_KEY`; `AUTH_COOKIE_SECURE` es `not DEBUG` por defecto |
| `TRUSTED_PROXY_COUNT` | Proxies de confianza delante de la app (`0` por defecto). Ver la advertencia arriba |
| `MAILER_BACKEND` | Correo: consola por defecto. `anymail.backends.resend.EmailBackend` exige `RESEND_API_KEY`; `django.core.mail.backends.smtp.EmailBackend` exige `MAILER_HOST`, `MAILER_USERNAME`, `MAILER_PASSWORD` (y admite `MAILER_PORT`, `MAILER_USE_TLS`) |
| `SENTRY_DSN`, `SENTRY_ENVIRONMENT` | Monitoreo de errores, opcional: solo se activa con `SENTRY_DSN` (no lo pongas en tu `.env` local al correr las pruebas: las activaría contra el proyecto real). `SENTRY_ENVIRONMENT` es `production` si `DEBUG` es falso y `development` si no. `init_sentry` (en `apps/common/sentry.py`) apaga usuario/IP/cookies, cuerpo de las peticiones, variables locales, breadcrumbs, métricas y tracing, y no propaga `sentry-trace` ni `baggage` en las llamadas salientes (por ejemplo al proveedor de correo). `scrub_event` deja pasar solo una lista de campos y descarta cualquier evento con forma inesperada. Lo que sí puede llegar a Sentry, y solo en errores: de la petición, el método, la **ruta** de la URL (nunca query ni fragmento; en una ruta que no resuelve es lo que envió el cliente) y las cabeceras `Host`, `User-Agent`, `Accept`, `Origin`, `Content-Type` y `Content-Length`; el nombre de la transacción (patrón de ruta o, si no resuelve, la ruta); de la excepción, tipo y traceback con el mensaje vacío; **el mensaje de log y sus parámetros tal cual, si los escribe un logger de `apps.`** (por eso no se ponen datos personales en logs, regla del proyecto); y metadatos (nivel, `environment`, `release`, `server_name`, versión de Python y del SDK). Los ids de traza no se envían |

### Configurar correo

`MAILER_BACKEND` decide cómo salen los correos (activación de cuenta, recuperación de
contraseña); ver la fila de la tabla de arriba para las variables de cada uno.

- **Consola** (default): no hay nada que configurar — el correo se imprime en la terminal del
  backend. No llega a ninguna bandeja real; sirve para desarrollo local.
- **SMTP** (`django.core.mail.backends.smtp.EmailBackend`): sirve con cualquier proveedor SMTP.
  Con Gmail: activa la verificación en dos pasos de la cuenta remitente, crea una
  [contraseña de aplicación](https://myaccount.google.com/apppasswords) y usa `smtp.gmail.com`,
  puerto `587`, con `MAILER_USE_TLS=True`.
- **Resend** (`anymail.backends.resend.EmailBackend`): crea una cuenta en
  [Resend](https://resend.com), saca una API key y ponla en `RESEND_API_KEY`. No usa
  `MAILER_HOST`/`USERNAME`/`PASSWORD`.

En cualquiera de los dos últimos, para probar de punta a punta: solicita la recuperación de
una cuenta activa registrada y revisa la bandeja (y spam) del correo real. El enlace apunta a
`FRONTEND_URL/restablecer-contrasena?uid=...&token=...`, vence en 30 minutos y es de un solo
uso — la forma exacta de la petición y la respuesta de cada endpoint están en el esquema
OpenAPI (`/api/docs`), no se repite aquí para no desalinearse de él. No guardes credenciales
reales de correo en archivos versionados.

El `Procfile` corre `migrate`, `flushexpiredtokens` y `collectstatic` antes de `gunicorn`.

## Cómo se trabaja en el día a día

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install                # ruff, black y el chequeo de tildes perdidas
cp .env.example .env              # completa las credenciales de tu PostgreSQL local
python manage.py migrate
python manage.py runserver
```

### Pruebas

- `pytest` + `pytest-django` + `factory-boy` (`pytest --cov` para la cobertura; la
  configuración está en `pyproject.toml`). Necesitan el mismo PostgreSQL del `.env`:
  pytest-django crea y borra su propia base `test_*`.
- Los tests viven en `apps/<app>/tests/test_*.py`, las fábricas en `apps/<app>/tests/factories.py`
  y los helpers de sesión en `apps/accounts/tests/helpers.py` (`csrf_client`, `open_session`,
  `login_by_email`…).
- Fixtures de `conftest.py`: `api_client` (se comporta como el navegador: exige CSRF y ya trae
  el token), `anonymous_client` (exige CSRF, sin token ni sesión) y `auth_client(user)` (abre una
  sesión real con las cookies JWT de ese usuario y devuelve el cliente). La caché se limpia
  entre pruebas porque los límites de solicitudes viven en ella.
- **TDD:** primero el test, verlo fallar por la razón correcta, luego el código. Un bug
  corregido lleva el test que lo habría atrapado. Se prueba comportamiento, no
  implementación, y se cubren los bordes reales: vacíos, límites, entradas hostiles,
  sin permiso, sin sesión, sesión vencida y las respuestas de error.
- **Sin datos personales reales:** correos `@example.com` y documentos inventados, armados con
  fábricas y helpers, no copiando el mismo `objects.create(...)` en cada test.
- Una prueba que renderiza una página HTML (el admin, por ejemplo) falla con "Missing
  staticfiles manifest entry" porque en pruebas no corre `collectstatic`: usa la fixture
  `plain_static_files` de `conftest.py`.

### Antes de proponer un PR

El agente corre todo esto con el entorno virtual activo y lo deja en verde; si algo falla, lo
corrige o lo dice en el PR, nunca lo omite:

```bash
pytest --cov -q
ruff check .
black --check .
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml
```

Después revisa el diff completo buscando bugs, como lo haría otra persona: casos borde,
código duplicado, archivos que hacen dos cosas, datos personales en logs, tests que no afirman
nada. Ruff y Black usan `line-length = 99`.

## Reglas de diseño

- **Ninguna opción gana por defecto.** Ante una necesidad se comparan las alternativas reales
  (lo que ya trae Django/DRF, una librería o código propio) y se elige por: cumple el
  requisito completo, costo de mantenerlo, salud de la dependencia (cada librería nueva es
  algo más que actualizar y auditar), encaje con lo existente y seguridad (en autenticación,
  criptografía y datos personales se prefiere lo probado por mucha gente). Lo que se decide se
  deja escrito, con lo que se descartó y por qué.
- **La misma lógica no aparece dos veces:** si va a repetirse, se extrae antes de integrar (un
  validador, un helper). Una responsabilidad por archivo.
- **Concurrencia:** restricción única en la base de datos y bloqueo optimista con `version`;
  toda operación que asigna un recurso escaso corre en `transaction.atomic`.
- **Fechas:** "hoy" es `django.utils.timezone.localdate()` (zona `America/Bogota`).
- **Datos personales:** ningún log, mensaje de error ni comentario los incluye. El mensaje de
  una excepción puede traer un correo o un documento (un `IntegrityError` con el valor
  duplicado, un fallo de envío con el destinatario), así que al registrar un fallo se escribe
  el `pk` y la clase, nunca el mensaje ni `exc_info`. El manejador global de errores no
  controlados registra la clase de la excepción y las líneas del traceback (archivo, línea,
  función y código de cada frame), sin el mensaje ni variables.
- **Trampas conocidas:**
  - Validar dígitos con `[0-9]` y `\Z`, no `\d` ni `$`: `\d` acepta dígitos de otros alfabetos y
    `$` acepta un salto de línea final, y dos documentos "distintos" burlan la unicidad.
  - Los validadores de campo corren antes de `clean()`: si `clean()` normaliza el valor
    (quita puntos y guiones), el validador del campo ya lo rechazó. Normaliza y valida en el
    mismo lugar.
  - Las plantillas de correo `.txt` llevan `{% autoescape off %}`; si no, el `&` del enlace
    llega como `&amp;` y el enlace se rompe. La `.html` sí lleva autoescape.
  - Una respuesta distinta (o un 500) cuando una cuenta existe permite enumerar cuentas: lo que
    envía correo o llama a un servicio externo responde igual pase lo que pase.
  - `except Exception` solo donde el objetivo lo exige (una respuesta uniforme) y siempre
    registrando; nunca para "que no falle".
