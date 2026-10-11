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
con WhiteNoise, geometría de polígonos con `shapely`, `gunicorn` como servidor y Sentry
opcional. Toda la configuración sale de
variables de entorno (`python-decouple`, ver "Variables de entorno").

| Ruta               | Qué contiene                                                                    |
| ------------------ | ------------------------------------------------------------------------------- |
| `config/`          | Ajustes, URLs raíz, WSGI/ASGI                                                   |
| `apps/common/`     | Lo transversal: `ApiError` y el manejador de errores, paginación, permisos por acción, CSRF, validadores, catálogo de municipios, área de un polígono (`geo.py`), base de los historiales de auditoría, bloqueo de la raíz de una finca (`locks.py`), guardado con restricción única (`db.py`), pasos comunes de editar con `version` (`versioning.py`) y de auditar la edición (`record_update_events`), middleware `no-store`, vistas 404/500 en JSON |
| `apps/accounts/`   | Usuario (se identifica por correo), sesión, recuperación de contraseña, bloqueo por intentos, eventos de autenticación |
| `apps/producers/`  | Productores: alta, consulta, edición y cambio de estado                         |
| `apps/farms/`      | Fincas: alta (también sin conexión), consulta, edición, activación y su auditoría, y los conteos y puntos del mapa por municipios. El productor y sus empleados ven las suyas; la asociación lee las de todos (`services/scope.py`) |
| `apps/plots/`      | Parcelas de cada finca: alta (también sin conexión), consulta, edición, activación, eliminación de lo creado por error (si nada depende de la parcela), contorno opcional y su auditoría, que sobrevive al borrado. Las reglas de área disponible y de superposición corren con la fila de la finca bloqueada |
| `apps/activities/` | Actividades agrícolas de cada parcela: programar, editar, reprogramar, eliminar lo programado por error, registrar la realización (también desde la cola sin conexión) y consultar por periodo, con su historial de valores anterior y nuevo. Los estados retrasada y vencida se calculan con la fecha (`state.py`); todo su alcance pasa por `services/queries.py` |
| `apps/crops/`      | Catálogo común de variedades de cacao (lo administra la asociación; viene cargado por una migración de datos) y la ficha agronómica de cada parcela: sus siembras (variedad, fecha, árboles, propagación y etapa; la misma variedad puede tener varias tandas), manejo y sombra. La ficha se registra o reemplaza completa (también sin conexión) y su historial guarda los valores de cada versión |
| `apps/inputs/`     | Catálogo de insumos agrícolas de cada productor (nombre, tipo, unidad y presentación): alta, consulta, edición, activación, eliminación de lo creado por error (si ningún registro lo usa) y un historial que guarda el valor anterior y nuevo de cada campo, que sobrevive al borrado; y su inventario por finca (existencias y movimientos de entrada, conteo y salida) |
| `apps/demo_data/` | Comando `seed_demo_data`: datos y cuentas de demostración, creados por los servicios de las demás apps |

### Capas

`views → services → models`, en una sola dirección:

- **views** (HTTP): reciben la petición, validan con serializers, aplican permisos y arman la
  respuesta. No tienen lógica de negocio.
- **services**: reglas y transacciones (`transaction.atomic`, `select_for_update`). No arman
  respuestas HTTP; un caso de negocio fallido se lanza como `ApiError`.
- **models**: datos, restricciones y validadores.

Lo que usa una sola app vive en esa app; lo transversal, o lo que ya necesita una segunda app,
sube a `apps/common`. Ninguna app importa de otra y `common` no importa de ninguna. La
única excepción es `apps/demo_data`, que arma datos que cruzan todas (como `config/` junta sus
rutas); ninguna app importa de ella. Un módulo
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
  `farm_id_conflict` o `plot_id_conflict` de un registro propio, con la versión del servidor;
  `measured_area_hectares` en el `area_mismatch`; `overlaps`, `suggested_boundary` y
  `suggested_measured_area_hectares` en el `plot_overlap`). Los errores de negocio son
  subclases de `ApiError`
  (su `default_code` es el `code`) y el manejador global de `apps/common/exceptions.py` arma el
  cuerpo: nunca se responde `Response({...})` a mano con otra forma. Una ruta que no existe
  bajo `/api/` (404) y un fallo no controlado (500, sin datos técnicos) responden con la misma
  forma (con `DEBUG=True`, Django muestra en su lugar su página técnica de depuración).
- **Códigos:** `validation_error`, `invalid_reset_token`, `parse_error`, `location_required`
  (400); `not_authenticated`, `authentication_failed`, `invalid_credentials` (401);
  `permission_denied`, `account_inactive`, `account_locked` (403); `not_found` (404);
  `method_not_allowed` (405); `not_acceptable` (406); `duplicate_document`, `stale_version`,
  `duplicate_farm_name`, `farm_id_conflict`, `farm_has_records`, `producer_has_records`,
  `duplicate_plot_code`, `plot_id_conflict`, `plot_has_records`, `duplicate_variety_name`, `account_has_activity`,
  `duplicate_input`, `input_has_records`, `movement_id_conflict` (409);
  `payload_too_large` (413); `unsupported_media_type` (415); `invalid_coordinates`,
  `location_outside_operating_area`, `municipality_department_mismatch`, `farm_inactive`,
  `farm_area_below_plots`, `invalid_boundary`, `area_mismatch`, `plot_area_exceeds_farm`,
  `plot_overlap`, `plot_too_far_from_farm`, `plot_inactive`, `variety_inactive`,
  `density_too_high`, `input_unit_locked`, `producer_inactive`, `input_inactive` (422);
  `throttled` (429); `internal_error` (500). El frontend decide qué hacer según `code`,
  no según `detail`.
- **Registros creados sin conexión** (hoy, fincas y parcelas): el `POST` acepta un `id` UUID generado en
  el dispositivo. Reenviar el mismo `id` con el mismo contenido responde `200` con el registro
  ya creado (nunca duplica, ni con dos envíos simultáneos); con otro contenido u otro dueño,
  `409`. Si el registro es del mismo dueño, ese `409` trae el del servidor en `current`: suele
  ser un pendiente editado en el dispositivo tras una creación cuya respuesta se perdió, y el
  cliente lo envía como `PATCH` con esa `version`. Si es de otro dueño, sin `current`, para no
  revelar sus datos. El `PATCH` exige `expected_version`; si el registro ya tiene exactamente lo que se
  pide (un reintento cuya respuesta se perdió) responde `200` sin cambios, y si no, `409
  stale_version`. `captured_at` (hora del dispositivo) es opcional e informativo: el orden y
  los conflictos se deciden con `version` y con la hora del servidor.
- **Un `DELETE` lleva la versión en la URL** (`?expected_version=N`), nunca en el cuerpo: HTTP no
  define su significado, algunos intermediarios lo descartan y el esquema OpenAPI no lo documenta.
  Es el caso de fincas y de productores.
- **Eliminar un productor creado por error** (`DELETE /api/producers/{id}`, `producers.delete`, no
  delegable): se elimina todo lo que depende de él si nada de eso es importante; si algo lo es
  responde `409 producer_has_records` y no se borra nada. Una app que agrega algo que depende de
  un productor lo declara con `register_dependent(ProducerDependent(...))` de
  `apps/common/producer_dependents.py` en su `ready()` (qué es "importante", cuántos hay, cómo se
  eliminan), como ya hacen `farms` y `accounts`: así `producers` no importa de ninguna. Deja un
  `ProducerAuditEvent` sin relación con el productor, que sobrevive. Los dependientes se eliminan
  **al revés de como se registraron** (fincas antes que cuentas): cada app se registra después de
  aquellas de las que depende, y lo que apunta a una cuenta con `PROTECT` (el responsable de una
  actividad) tiene que irse antes que ella.
- **La altitud de una finca debe caber en el terreno de su municipio**, con 100 m de margen y sin
  bajar de 0 (`apps/common/municipality_altitude.py`, calculado sobre un modelo de elevación de
  30 m; el frontend usa la misma tabla). Solo se exige al crear y cuando cambian la altitud o el
  municipio: una finca guardada antes de la regla puede seguir desactivándose o corrigiendo sus
  otros datos. Un vértice de parcela tampoco puede quedar a más de
  `2 × √(área de la finca ÷ π) + 300 m` del punto de la finca (`422 plot_too_far_from_farm`).
- **Eliminar una cuenta creada por error** (`DELETE /api/users/{id}`, `accounts.users_delete`,
  delegable, `204`, sin `version`): solo la que nunca inició sesión (`last_login` vacío), sea
  empleado, Productor o Administrador. Una que ya entró responde `409 account_has_activity` y se
  desactiva en su lugar; el último administrador activo, `409 last_administrator`. Rigen las mismas
  reglas de acceso que al desactivar. Los historiales donde la cuenta era actor quedan con el actor
  en nulo, y el evento `account_deleted` guarda solo su id (`target_user_ref`, sin FK). Una tabla
  nueva que apunte a la cuenta usa `SET_NULL` o `PROTECT`; con `PROTECT` la cuenta no se elimina.
  La cuenta expone `has_signed_in` para que el frontend sepa si ofrecer eliminar.
- **Eliminar una finca sigue el mismo patrón:** sus parcelas se eliminan con ella si ninguna
  tiene registros; si alguna los tiene, `409 farm_has_records` y no se borra nada. `plots` lo
  declara con `register_dependent(FarmDependent(...))` de `apps/common/farm_dependents.py`. Una
  tabla que apunte a la finca sin estar registrada también la bloquea. **Eliminar una parcela**
  consulta igual su propio registro (`apps/common/plot_dependents.py`): `activities` se registra
  ahí, y las actividades sin realizar se van con la parcela, cada una con su evento `deleted`;
  una realizada responde `409 plot_has_records`. Como el borrado de una finca pasa por el de sus
  parcelas, la regla vale también para fincas y productores. Lo que apunta a la parcela sin
  registrarse (la ficha) sigue bloqueándola. Los tres registros salen de
  `apps/common/dependents.py`.
- **Paginación única:** `page` (desde 1) y `page_size` (1–100, 20 por defecto); respuesta
  `{"count", "next", "previous", "results"}`. Una página fuera de rango responde 404
  `not_found`.
- **La búsqueda de productores ignora mayúsculas y tildes** (`perez` encuentra `Pérez`) con
  la extensión `unaccent` de PostgreSQL, que habilita una migración de `producers`: el usuario
  de la base de datos necesita permiso para crear extensiones (`unaccent` es de confianza
  desde PostgreSQL 13, no exige ser superusuario).
- **Todas las respuestas bajo `/api/` llevan `Cache-Control: no-store`** (traen datos
  personales).
- **La ficha de una parcela se guarda con `PUT /api/plot-characterizations/{id}`**, donde `id` es
  el de la parcela (hay una sola ficha por parcela, y la cola del dispositivo la sincroniza por
  ese `id`). Lleva siempre `expected_version`: `null` para registrar y la versión leída para
  editar. Responde `201` al crear y `200` al reemplazar o si la ficha ya tenía exactamente ese
  contenido (un reintento, sin subir la versión); si no coincide, `409 stale_version` con la
  ficha vigente, o `null`, en `current`. Las filas son siembras (`plantings`: variedad, mes,
  árboles, `propagation` y `stage`), sin repetir la misma variedad en el mismo mes. La etapa es de
  cada siembra y no de la ficha: en una renovación gradual conviven etapas distintas. Una variedad que no existe es un `400`
  en `fields.plantings` y no un `404`: la cola lee un `404` como registro eliminado y descartaría
  la ficha. Más de 10.000 árboles/ha sobre el área declarada de la parcela es `422
  density_too_high` (1 m² por árbol: atrapa el cero de más sin bloquear siembras reales). El
  listado (`GET /api/plot-characterizations`) exige `farm`, `plots` (ids separados por coma,
  hasta 100) o los dos, y no se pagina. Consultar pide `plots.view_plot`; la asociación no lee
  fichas.
- **La lista de parcelas** (`GET /api/plots`) filtra por `characterization` (`done` o `pending`)
  y trae `characterization_counts` (`{done, pending}`) junto a `count`, calculados con todos los
  filtros menos ese, para el contador de la interfaz. `ordering` es `code` o
  `producer,farm,code` (para agrupar), con desempate por id en cada nivel. Si una parcela tiene
  ficha lo dice `crops` con un `Exists` que registra en `apps/common/plot_characterization.py`
  desde su `ready()`: `plots` lo usa sin conocer el modelo de fichas.
- **El historial de una ficha** (`GET /api/plot-characterizations/{id}/history`, paginado, de la
  versión más nueva a la más vieja) devuelve, por versión, `version`, quién la guardó
  (`actor_name`, `null` si la cuenta se eliminó), los campos que cambió y los valores que dejó
  (`snapshot`). Pide `plots.view_plot` y se limita a las parcelas del productor de la sesión
  (`404` si no es suya). Cada evento guarda la `version` de la ficha que dejó, para que cosecha
  pueda referirse a una.
- **Una tabla que apunta a la parcela la vuelve importante:** la ficha (y su historial) impide
  eliminar la parcela, su finca o su productor, sin que `plots` sepa nada de `crops`, porque el
  borrado recorre todas las relaciones del modelo (`apps/common/db.py`).
- **El catálogo de variedades** (`/api/cacao-varieties`) solo pide sesión para consultarlo y no
  se pagina. Registrar, editar, activar y desactivar piden `crops.manage_cacaovariety`, que no es
  delegable. El nombre se compara sin mayúsculas, tildes, espacios ni guiones (también los de
  Unicode): `CCN-51`, `CCN 51` y `ccn51` son la misma variedad. Cada variedad tiene además hasta
  5 nombres comunes (`common_names`), que **sí se repiten entre variedades** (de un mismo lugar
  salen varios clones: "Saravena" son los tres FSA) y que la búsqueda también compara.
- **El catálogo de insumos** (`/api/agricultural-inputs`) es de cada productor y se entrega completo,
  activos e inactivos, en `{"results": [...]}` sin paginar: la búsqueda y los filtros corren en el
  dispositivo. Los permisos son `inputs.{view,add,change,delete}_agriculturalinput`, delegables; el
  Capataz/Operario recibe los tres primeros y la asociación ninguno (`403`). Un insumo de otro
  productor es `404`. El nombre se compara sin mayúsculas, tildes, espacios ni guiones, dentro del
  mismo tipo (`409 duplicate_input` con el existente en `existing`, también si está inactivo). La
  unidad es kg, g, l, ml o unidades; la presentación (`package_type` y `package_size`, de 0,001 a
  100.000) es opcional, va completa o no va y se quita enviando los dos en `null`. `has_records` dice
  si algo lo usa, recorriendo las relaciones del modelo (`usage.py`) sin que `inputs` conozca a las
  demás apps: mientras sea cierto, la unidad no cambia (`422 input_unit_locked`; la presentación sí)
  y el insumo no se elimina (`409 input_has_records`);
  una tabla nueva que apunte a un insumo usa `PROTECT` y bloquea la fila del insumo al guardar.
  Registrar es solo en línea (el servidor genera el `id`) y `POST` acepta `producer_id` solo de la
  cuenta técnica (`422 producer_inactive` si el productor está inactivo). Eliminar lleva
  `expected_version` en la URL; los insumos de un productor creado por error se eliminan con él.
- **El inventario de insumos** se lleva por finca. `InputStock` es el saldo de un insumo en una finca
  (puede ser negativo: faltan entradas por registrar) y `InputMovement`, cada movimiento: entrada,
  conteo o salida por actividad. El saldo siempre es la suma de los `quantity` de sus movimientos,
  y los movimientos no se editan ni se borran: un error se corrige con un conteo. Todo pasa por
  `services/movements.py`, que bloquea siempre en el mismo orden (finca, insumo, existencias).
  `GET /api/input-stocks` (sin paginar; `farm` opcional: con ella las de esa finca, sin ella una fila por insumo y finca de todo el alcance para sumar el total; finca ajena, lista vacía; `producer` solo lo usa la cuenta técnica) y `GET
  /api/input-movements?input=&farm=` (paginado; ajenos, `404`) piden `view_agriculturalinput`.
  `POST /api/input-movements` pide `inputs.manage_inputstock` y acepta solo `entry` y `count`; un
  `id` repetido con el mismo contenido responde `200` sin duplicar, con otro, `409
  movement_id_conflict`. Un conteo calcula su diferencia contra el saldo del momento de guardar, y se rechaza si su fecha es anterior a un movimiento ya registrado (dejaría las existencias en lo contado y borraría el efecto de ese movimiento): la persona cuenta de nuevo con la fecha de hoy. Las
  salidas las registra el sistema: otra app descuenta lo que gasta una labor con
  `AgriculturalInput.record_consumption(farm, quantity, occurred_on, note, actor)` (cantidad en
  positivo, dentro de su propia transacción, sin validar existencias ni estados: una labor ya hecha
  no se rechaza). Una finca con movimientos no se elimina (`farm_has_records`), porque la
  restricción `PROTECT` las cuenta sola.
- **El historial de un insumo** (`AgriculturalInputAuditEvent`) guarda por cada campo cambiado su
  valor anterior y nuevo (`changes`), a diferencia de los demás historiales: un insumo no tiene datos
  personales. Lo calcula `field_changes` (`apps/common/audit.py`), la misma función que usan las
  actividades: un historial nuevo con valores la reutiliza en vez de escribir la suya. Es de solo lectura y solo para superusuarios en el admin, y el evento `deleted` guarda
  `input_ref` e `input_name` para sobrevivir al insumo.
- **Las actividades agrícolas** (`/api/agricultural-activities`):
  - **Estados:** se guardan `scheduled` y `done`; la API entrega además `state` y `days_late`,
    calculados con la fecha de Bogotá: `delayed` el día 1 y 2 de atraso y `overdue` desde el
    tercero (`OVERDUE_AFTER_DAYS`, el frontend tiene la misma constante). Retrasada se edita,
    reprograma y elimina; vencida solo se registra (`409 activity_overdue`); realizada no se toca
    (`409 activity_already_done`).
  - **Programar** (`POST`, `id` del cliente, reenvío idéntico `200`) solo en parcela y finca
    activas; `phytosanitary_control` es `422 activity_type_not_allowed` (se crea desde un
    monitoreo). **Editar** (`PATCH` con `expected_version`) valida la fecha, el responsable y el
    tipo solo si cambian.
  - **Registrar la realización** (`POST …/{id}/completion`) llega desde la cola: no pide versión,
    el mismo envío responde `200` sin cambios y otra fecha sobre una realizada es
    `activity_already_done`. Un monitoreo es `422 monitoring_requires_result`.
  - **Insumos de la realización** (`inputs`: ninguno, uno o varios, sin repetir): cada uno se
    descuenta del inventario de la finca con `record_consumption`, en la misma transacción, con la
    nota `{labor} · {código de la parcela}` que muestra Insumos ("Fertilización · P-03"; con Otro,
    su descripción). Las existencias pueden quedar negativas. Bloqueo: la finca, los insumos por
    id y sus existencias, el mismo orden que el inventario. El reenvío idéntico no vuelve a
    descontar. Un insumo inactivo es `422 input_inactive` con `input_ids`; uno que no es del
    catálogo del productor, `400` (no `404`: la cola lo leería como actividad eliminada). Una
    actividad de tipo Inventario no lleva insumos.
  - **Listado** (`GET ?from=&to=`) de hasta 120 días, sin paginar; **responsables**
    (`GET …/assignees`) con solo id, nombre y si está activa.
  - El responsable (`assignee`) es `PROTECT`: una cuenta responsable de alguna actividad no se
    elimina (`account_has_activity`).
  - El historial guarda `changes` con el valor anterior y el nuevo de cada campo
    (`field_changes`, `apps/common/audit.py`); una persona va por su id, nunca por su nombre.
- **Esquema OpenAPI** con `drf-spectacular`: `GET /api/schema` y Swagger en `/api/docs`, **solo
  con `DEBUG=True`**. Las vistas declaran sus respuestas de error con `error_responses(...)`
  (`apps/common/schema.py`) para que el esquema traiga la forma estándar. El frontend debe
  generar sus tipos con `openapi-typescript` a partir de este esquema y no escribirlos a mano:
  un endpoint o campo nuevo debe quedar reflejado en el esquema en el mismo PR.
  Se valida con `python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml`.
  Un campo con opciones que se llame igual que otro de otro recurso (`status`) lleva su nombre
  fijo en `ENUM_NAME_OVERRIDES` (`config/settings.py`): si no, spectacular renombra alguno con un
  sufijo generado y los tipos del frontend dejan de compilar.

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
- **Cada rol trae sus permisos con su nombre** (`permission_details`: `code` y `name`), además de
  la lista de códigos (`permissions`). `/api/permissions` solo ofrece los delegables, que son los
  que puede llevar un rol propio, así que no sirve para nombrar los de un rol del sistema.
- **Todo permiso nuevo se declara en `apps/accounts/registry.py` y es delegable por defecto.**
  Si actúa sobre el espacio de un productor (sus fincas, sus cuentas, su operación), el
  productor puede dárselo a un empleado de confianza en un rol propio. Solo se marca
  `delegable=False` con la razón escrita al lado, por ejemplo que actúe sobre toda la
  asociación (`producers.*`). La cuenta Productor no se protege con un permiso sino con una
  regla (`ensure_can_manage_account`), porque todo lo que el rol Productor tiene es delegable.
  Un permiso de acción declara además su dependencia de
  vista en `PERMISSION_DEPENDENCIES` (crear o editar sin poder consultar no sirve). Un código
  que no está en el registro queda no delegable, pero eso es una red contra el olvido, no la
  forma de decidirlo.
- **El productor lo dice el recurso.** Un servicio que busque algo que ya existe (una finca, una
  parcela, una ficha) usa `owner_filter(actor, campo)` y `owns(actor, productor)`
  (`apps/common/ownership.py`), nunca `actor.producer_id` como filtro: el productor y su gente
  alcanzan lo suyo, y la cuenta técnica (superusuario, sin productor propio) alcanza lo de cualquiera.
  Una prueba (`apps/common/tests/test_ownership_guard.py`) falla si un servicio de fincas, parcelas o
  fichas filtra directo por el productor del actor. Lo que se crea y no cuelga de nada que ya exista
  lleva el productor en el cuerpo: `POST /api/farms` acepta `producer_id` **solo** de la cuenta
  técnica (y debe existir y estar activo); de cualquier otra cuenta es un `400`. Insumos hace lo mismo y comparte `resolve_target_producer`
  (`apps/common/ownership.py`). La auditoría registra siempre a quien actuó.
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
  `producers.change_status`, `producers.delete`), no a los que Django genera. No se puede crear ni
  borrar desde el admin (el alta asigna el código de asociado y detecta el documento repetido; al
  productor se le cambia el estado, y solo la API elimina uno creado por error). Se editan nombre, teléfono, correo, municipio y fecha de
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
- **`seed_demo_data`** (management command) carga productores, fincas, parcelas y fichas
  inventados y deja dos cuentas con contraseña pública (`administrador@example.com` y
  `productor@example.com`, la misma que muestra la pantalla de inicio de sesión del frontend).
  Es idempotente: no toca un productor que ya existe y restablece las dos cuentas. No envía
  correos. Nunca se corre en un despliegue con datos reales.
- Todo cambio desde el admin pasa por `services` y sube `version`: la ficha lleva la versión con
  la que se abrió y, si otra persona la cambió antes, no se guarda.
- **Variedades de cacao** (`apps/crops/admin.py`): con `crops.manage_cacaovariety`. Alta, edición
  y borrado pasan por los servicios, que normalizan el nombre y dejan el historial. Solo se borra
  una variedad que ninguna ficha usa (registrada por error); el historial sobrevive y registra el
  borrado. No llevan `version`: dos ediciones simultáneas del catálogo no se contemplan, porque
  la asociación va a tener una sola cuenta Administrador.
- **Historial de las fichas** (`PlotCharacterizationAuditEvent`): de solo lectura y solo para
  superusuarios. El admin no filtra por productor, así que con `plots.view_plot` un empleado
  vería las fichas de todos, y la asociación no lee fichas.
- **Historial de los insumos** (`AgriculturalInputAuditEvent`): de solo lectura y solo para
  superusuarios, por la misma razón: el admin no filtra por productor. Se ve el valor anterior y
  nuevo de cada campo cambiado.
- **Historial de las actividades** (`AgriculturalActivityAuditEvent`): igual, de solo lectura y
  solo para superusuarios, con el valor anterior y el nuevo de cada cambio.

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

#### Si el correo llega a spam

Los correos de activación y de recuperación **pueden caer en la carpeta de spam**, sobre todo en
buzones institucionales (Microsoft, Google), que son estrictos con un dominio recién verificado y
con poco historial. El código ya hace lo suyo: remitente con nombre visible (`Ruta del Cacao
<dirección>`), versión de texto y de HTML, y el enlace escrito completo por si el botón se
bloquea. Lo que falta es del lado del dominio, y se revisa en el panel del proveedor:

- **`DEFAULT_FROM_EMAIL` debe ser una dirección del dominio verificado** en Resend; con otra, el
  proveedor rechaza el envío o el correo sale con un remitente que no coincide con su firma.
- **SPF, DKIM y DMARC en el DNS del dominio.** SPF y DKIM los entrega Resend al verificar el
  dominio (ambos deben figurar como verificados); DMARC es un registro TXT en `_dmarc.<dominio>`,
  por ejemplo `v=DMARC1; p=none; rua=mailto:alguien@<dominio>`, y se endurece cuando los reportes
  muestren que todo pasa.
- **Sin rastreo de aperturas ni de clics** en la configuración del dominio: reescribe el enlace
  a otro dominio, y un enlace de activación que apunta a un tercero es justo lo que los filtros
  sospechan.
- **`FRONTEND_URL` en el mismo dominio** que el remitente (o un subdominio suyo): el enlace del
  correo y la dirección de envío alineados puntúan mejor.
- Para medir, enviarse una activación a una dirección de [mail-tester.com](https://www.mail-tester.com)
  y leer su reporte (SPF/DKIM/DMARC y contenido).

Mientras no haya historial de envío, quien reciba el correo debe **revisar spam** y marcarlo
como "no es spam"; la aplicación se lo recuerda al enviar. Las cuentas de demostración no
dependen del correo.

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
  - **Toda escritura bajo una finca bloquea solo la finca** (`lock_aggregate_root`,
    `apps/common/locks.py`), y nunca además la fila de abajo (la parcela, la ficha, la cosecha).
    La finca es la raíz de todo lo que cuelga de ella: con un único bloqueo no puede haber dos
    operaciones esperándose entre sí, y una entidad nueva no tiene que acordarse de ningún orden.
    El costo es que dos escrituras bajo la misma finca se atienden una tras otra, y duran
    milisegundos. Una app nueva que escriba sobre algo de una finca (cultivos, cosecha, lotes)
    toma ese bloqueo antes de leer lo que va a cambiar, con `root="plot__farm"` si cuelga de una
    parcela. Si algún día contendiera de verdad, se agregan bloqueos más finos *por debajo* de
    este, sin romper nada. **Excepción deliberada, el inventario de insumos:** un movimiento
    bloquea la finca, el insumo y sus existencias, siempre en ese orden. Las actividades descuentan
    lo que gastan con el mismo orden (finca primero, que ya tienen bloqueada), y con un orden fijo
    no hay esperas cruzadas. Un flujo nuevo que bloquee un insumo debe tomar antes la finca.
  - **Dentro de un bloqueo no va nada lento:** subir una foto o un archivo, llamar a un servicio
    externo o generar un reporte se hace antes o después, fuera de la transacción. Un archivo se
    sube primero y una transacción corta registra sus metadatos; si no, se retienen una conexión
    de la base y el bloqueo de la finca mientras dura la subida.
  - **Guardar un registro con una restricción única** (un nombre o un código repetido) se hace
    con `save_translating_unique` (`apps/common/db.py`): punto de guardado propio, el choque se
    traduce al error de negocio y cualquier otro se relanza. En las altas que se reintentan sin
    conexión, `find_existing` decide primero si el `id` ya existía, porque un reenvío no es un
    nombre repetido.
  - **Editar un registro con `version`** se arma con las piezas de `apps/common/versioning.py` y
    `record_update_events` de `apps/common/audit.py`, sin repetir sus pasos en cada servicio:
    `check_expected_version` (versión leída frente a la del registro bloqueado, y reintento de una
    cola sin conexión que ya se aplicó), `save_next_version` (sube la versión y guarda traduciendo la
    restricción única) y `record_update_events` (`UPDATED` por contenido y `STATUS_CHANGED` por
    `is_active`). Lo que sigue en cada servicio es lo que lo distingue: sus validaciones y cómo
    calcula `changed`. Un servicio que no encaja (la ficha reemplaza todo su contenido, y
    `producers` no tiene auditoría ni `current` en el conflicto) no se tuerce para usarlas.
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
