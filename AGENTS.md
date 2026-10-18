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
| `apps/common/`     | Lo transversal: `ApiError` y el manejador de errores, paginación, permisos por acción, CSRF, validadores, catálogo de municipios, área de un polígono (`geo.py`), base de los historiales de auditoría, bloqueo de la raíz de una finca (`locks.py`), guardado con restricción única (`db.py`), pasos comunes de editar con `version` (`versioning.py`) y de auditar la edición (`record_update_events`), middleware `no-store`, vistas 404/500 en JSON, el almacenamiento de archivos en la base (`storage.py`, con su tabla `StoredFile`) los puntos de encuentro de la representación de una actividad (`activity_details.py`, `activity_representation.py`), el de las alertas (`alerts.py`: evaluadores y `notify`) y quién puede programar en una finca (`schedulers.py`) |
| `apps/accounts/`   | Usuario (se identifica por correo), sesión, recuperación de contraseña, bloqueo por intentos, eventos de autenticación |
| `apps/producers/`  | Productores: alta, consulta, edición y cambio de estado                         |
| `apps/farms/`      | Fincas, con su código consecutivo por productor (`F02`): alta (también sin conexión), consulta, edición, activación y su auditoría, y los conteos y puntos del mapa por municipios. El productor y sus empleados ven las suyas; la asociación lee las de todos (`services/scope.py`) |
| `apps/plots/`      | Parcelas de cada finca, con su código consecutivo por finca (`P05`) y un nombre opcional: alta (también sin conexión), consulta, edición, activación, eliminación de lo creado por error (si nada depende de la parcela), contorno opcional y su auditoría, que sobrevive al borrado. Las reglas de área disponible y de superposición corren con la fila de la finca bloqueada |
| `apps/activities/` | Actividades agrícolas de cada parcela: programar, editar, reprogramar, eliminar lo programado por error, registrar la realización (también desde la cola sin conexión) y consultar por periodo, con su historial de valores anterior y nuevo. Los estados retrasada y vencida se calculan con la fecha (`state.py`); todo su alcance pasa por `services/queries.py` |
| `apps/crops/`      | Catálogo común de variedades de cacao (lo administra la asociación; viene cargado por una migración de datos) y la ficha agronómica de cada parcela: sus siembras (variedad, fecha, árboles, propagación y etapa; la misma variedad puede tener varias tandas), manejo y sombra. La ficha se registra o reemplaza completa (también sin conexión) y su historial guarda los valores de cada versión |
| `apps/inputs/`     | Catálogo de insumos agrícolas de cada productor (nombre, tipo, unidad y presentación): alta, consulta, edición, activación, eliminación de lo creado por error (si ningún registro lo usa) y un historial que guarda el valor anterior y nuevo de cada campo, que sobrevive al borrado; y su inventario por finca (existencias y movimientos de entrada, conteo y salida) |
| `apps/harvests/`   | Cosechas: una recolección en una parcela y fecha, con su peso en verde, su variedad (de la ficha de la parcela) y su recolector. Registrar (también desde la cola sin conexión), consultar por mes, corregir y eliminar mientras no formen un lote, con su historial de valor anterior y nuevo |
| `apps/lots/`       | Lotes: el lote de una cosecha, con su código de trazabilidad (`000123-F02-P05-261014-1`), su consecutivo por parcela y día que no se recicla y la cadena de estados que fermentación y secado usan sin redefinirla (`advance_lot_status`). Conformar es solo en línea |
| `apps/health/`     | Sanidad de las parcelas: el catálogo de plagas y enfermedades (lo administra la asociación; viene cargado por una migración de datos), el resultado de un monitoreo (detecciones con su incidencia, o sin presencia), los controles fitosanitarios unidos a una detección, el historial fitosanitario de una parcela, las detecciones que esperan un control y las fotos de evidencia. El monitoreo y el control son actividades de `activities`: esta app guarda lo suyo y cambia la actividad por métodos del modelo |
| `apps/notifications/` | Alertas y notificaciones: los avisos de cada persona (actividad próxima, retrasada y vencida; control pendiente), la bandeja (leer, marcar, eliminar y deshacer), el comando `evaluate_alerts` que corre cada hora y las notificaciones push (suscripciones por dispositivo y envío con `pywebpush`). Las condiciones las calcula cada app con su evaluador (`activities/alerts.py`, `health/alerts.py`) |
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
  (`not_acceptable`). **La única excepción** es subir una foto de evidencia
  (`POST /api/agricultural-activities/{id}/evidence`), que recibe `multipart/form-data` con
  `MultiPartParser` solo en esa vista: una foto en base64 pesaría un tercio más y se cargaría
  entera en memoria. Y la única respuesta que no es JSON es el archivo de una foto
  (`GET /api/evidence/{id}/file`).
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
  `duplicate_plot_name`, `plot_id_conflict`, `plot_has_records`, `duplicate_variety_name`, `account_has_activity`,
  `duplicate_input`, `input_has_records`, `movement_id_conflict`, `farm_has_accounts`, `account_has_pending_work`,
  `input_shared`, `harvest_in_lot`, `harvest_already_in_lot`, `harvest_id_conflict`,
  `lot_id_conflict`, `lot_invalid_status`, `duplicate_pest_disease_name`, `evidence_requires_done`,
  `evidence_limit_reached` (409), `role_scope_conflict` (400), `role_in_use_outside_scope` (403),
  `role_scope_in_use` (409);
  `payload_too_large`, `evidence_too_large` (413); `unsupported_media_type`,
  `evidence_format_not_allowed` (415); `invalid_coordinates`,
  `location_outside_operating_area`, `municipality_department_mismatch`, `farm_inactive`,
  `farm_area_below_plots`, `invalid_boundary`, `area_mismatch`, `plot_area_exceeds_farm`,
  `plot_overlap`, `plot_too_far_from_farm`, `plot_inactive`, `variety_inactive`,
  `density_too_high`, `input_unit_locked`, `producer_inactive`, `input_inactive`,
  `plot_not_characterized`, `variety_not_in_plot`, `collector_not_available`,
  `pest_disease_inactive`, `not_a_monitoring`, `evidence_not_allowed` (422);
  `throttled` (429); `internal_error` (500). El frontend decide qué hacer según `code`,
  no según `detail`.
- **Registros creados sin conexión** (fincas, parcelas y cosechas): el `POST` acepta un `id` UUID generado en
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
    tipo solo si cambian. El tipo de un control no cambia (`422 activity_type_not_allowed`):
    quedaría unido a la detección sin atenderla.
  - **Registrar la realización** (`POST …/{id}/completion`) llega desde la cola: no pide versión,
    el mismo envío responde `200` sin cambios y otra fecha sobre una realizada es
    `activity_already_done`. Un monitoreo es `422 monitoring_requires_result`: se registra con su
    resultado en `POST …/{id}/monitoring` (sanidad).
  - **Insumos de la realización** (`inputs`: ninguno, uno o varios, sin repetir): cada uno se
    descuenta del inventario de la finca con `record_consumption`, en la misma transacción, con la
    nota `{labor} · {código de la parcela}` que muestra Insumos ("Fertilización · P-03"; con Otro,
    su descripción). Las existencias pueden quedar negativas. Bloqueo: la finca, los insumos por
    id y sus existencias, el mismo orden que el inventario. El reenvío idéntico no vuelve a
    descontar. Un insumo inactivo es `422 input_inactive` con `input_ids`; uno que no es del
    catálogo del productor, `400` (no `404`: la cola lo leería como actividad eliminada). Una
    actividad de tipo Inventario no lleva insumos.
  - **Listado** (`GET ?from=&to=`) de hasta 120 días, sin paginar; **pendientes**
    (`GET …/pending?through=`, y `activity_type=` para quedarse con un tipo) las que siguen sin realizar
    hasta esa fecha, sin fecha mínima ni paginar, para que una vencida vieja no se pierda por el límite del listado; **responsables**
    (`GET …/assignees`) con id, nombre, si está activa, sus fincas y si se le puede asignar.
  - El responsable (`assignee`) es `PROTECT`: una cuenta responsable de alguna actividad no se
    elimina (`account_has_activity`).
  - El historial guarda `changes` con el valor anterior y el nuevo de cada campo
    (`field_changes`, `apps/common/audit.py`); una persona va por su id, nunca por su nombre.
  - **Lo que otra app hace sobre una actividad** pasa por métodos del modelo, como
    `record_consumption` de insumos, sin importar `activities`: `ensure_completable_by(actor)`,
    `complete_with_result` (cerrar un monitoreo), `schedule_control` y `record_done_control`
    (crear un control), `with_representation(queryset)` (las precargas para listarlas) y
    `state_today()`. Lo que hacen está en `services/linked.py`.
  - **La representación crece sin que `activities` conozca a quien la amplía:** otra app registra
    en `apps/common/activity_details.py` sus campos (una función que crea un serializer leído de
    la actividad) y sus rutas de precarga; el serializer los suma en `get_fields()`, y así el
    esquema los documenta tipados. Sanidad agrega `monitoring` y `control_of`. En la otra
    dirección, `activities` registra su serializer en `apps/common/activity_representation.py`
    para que sanidad responda con la actividad completa.
- **Código de finca y de parcela:** el servidor asigna a cada finca un número consecutivo dentro de
  su productor (`Farm.number`, código `F02`) y a cada parcela uno dentro de su finca (`Plot.number`,
  código `P05`; al menos dos cifras, `P100` la centésima). El contador vive en la fila del dueño
  (`Producer.farm_sequence`, `Farm.plot_sequence`), solo sube y se toma con `next_number`
  (`apps/common/codes.py`), que bloquea esa fila: un registro eliminado no devuelve su número, un
  reenvío o un rechazo no gastan uno y dos altas a la vez no repiten. Se asigna al llegar al
  servidor, así que un registro creado sin conexión recibe su código al sincronizar. `code` es de
  solo lectura (en la parcela, un `PATCH` con `code` es `400`). El nombre de la finca ya existía; el
  de la parcela (`Plot.name`) es opcional, de hasta 60 caracteres, único por finca solo cuando
  existe (`409 duplicate_plot_name`) y reemplaza al código libre de antes: una cola de una versión
  anterior que manda `code` sin `name` lo guarda como nombre, y con `name` lo ignora. La búsqueda de
  fincas y parcelas encuentra por código (`F02`, `f2`) y por nombre. La nota del inventario de una
  labor (`Fertilización · P05`) y los historiales nuevos usan el código.
- **Las cosechas** (`/api/harvests`): una recolección en una sola parcela y fecha, con su peso en
  verde (cacao en baba, `Decimal(7,1)`), su variedad y su recolector. Permisos
  `harvests.{view,add,change,delete}_harvest`, delegables; `delete` solo lo tiene el Productor y
  los cuatro son permisos de campo. El `POST` llega desde la cola (`id` del dispositivo, reenvío
  idéntico `200` sin volver a validar, otros datos `409 harvest_id_conflict`) y exige una parcela
  con ficha y siembras (`422 plot_not_characterized`), una variedad de esas siembras (`422
  variety_not_in_plot`), un recolector que cumple la regla de `apps/common/assignable.py`
  (`422 collector_not_available`), una fecha no futura ni anterior a la siembra más antigua de la
  variedad y un peso mayor que cero, de un decimal y de hasta 2.000 kg por hectárea declarada. Una
  parcela o finca inactivas no impiden registrar. Guarda la versión vigente de la ficha
  (`characterization_version`, que cambia si se corrige la variedad). El listado
  (`GET ?from=&to=`) es de hasta 92 días, sin paginar, con `farm`, `plot` y `producer` (solo la
  cuenta técnica); los filtros de variedad, recolector y lote y los totales corren en el
  dispositivo. `GET …/collectors` entrega las cuentas que pueden ser recolectoras, con la forma de
  los responsables de una actividad. Corregir (`PATCH` con `expected_version`) y eliminar
  (`DELETE ?expected_version=`) solo mientras no formen un lote (`409 harvest_in_lot`); cada regla se
  revisa solo si lo que mira cambia. Una cosecha impide eliminar su parcela, su finca y su productor
  (`plot_has_records` y siguientes), una cuenta recolectora (`account_has_activity`) y una variedad
  del catálogo. Su historial (`HarvestAuditEvent`) guarda el valor anterior y nuevo de cada campo.
- **Los lotes** (`/api/lots`): un lote es una cosecha completa (`OneToOne`). Permisos
  `lots.{view,add,delete}_lot`, delegables y de campo; consultar depende de consultar cosechas.
  Conformar (`POST`, solo en línea) asigna el código `PPPPPP-Fnn-Pnn-AAMMDD-c` (productor, finca,
  parcela, fecha de la cosecha y consecutivo de la parcela en ese día, `build_lot_code`) con la finca
  bloqueada; el consecutivo vive en `LotCodeSequence`, no baja al eliminar un lote y se reserva en
  la misma transacción que lo usa. El reenvío del mismo `id` para la misma cosecha es `200`; una
  cosecha que ya tiene lote, `409 harvest_already_in_lot` con ese lote en `current`. El listado es
  paginado, con `status`, `farm`, `plot`, `variety`, `from`, `to` (fecha de la cosecha), `search` por
  parte del código y `producer` (solo la cuenta técnica). Eliminar (`DELETE ?expected_version=`) solo
  un lote Generado (`409 lot_invalid_status` con `current_status`): la cosecha queda sin lote y el
  código no se reutiliza. **El estado** es `generated`, `fermenting`, `fermented`, `drying`, `dried`
  y solo cambia por `advance_lot_status(lot, expected, new, actor=...)` (`apps/lots/services/
  status.py`), que exige estar en `expected` y que `new` sea el siguiente; los demás módulos la
  llaman dentro de su transacción con el lote ya bloqueado (la finca de su parcela). El historial
  (`LotAuditEvent`) guarda el código y la cosecha de origen y sobrevive al lote.
- **Sanidad** (`apps/health`):
  - **Catálogo de plagas y enfermedades** (`/api/pests-diseases`): como el de variedades, solo pide
    sesión para consultarlo y no se pagina; registrar, editar, activar y desactivar piden
    `health.manage_pestdisease`, que no es delegable (es de toda la asociación). El nombre se
    compara sin mayúsculas, tildes, espacios ni guiones, y la búsqueda incluye el nombre
    científico. Cada una puede traer `suggested_sampling_unit` (árboles o mazorcas) y
    `suggested_control_method`, opcionales: la planilla del monitoreo los propone al elegirla y
    quien registra puede cambiarlos; la migración inicial los llena para las 12 del catálogo sin
    pisar lo que la asociación ya haya elegido. Sin historial. No se elimina por la API; desde el admin, solo una que ningún
    monitoreo usa.
  - **Resultado del monitoreo** (`POST /api/agricultural-activities/{id}/monitoring`): tipo de
    muestreo (árboles o mazorcas), unidades evaluadas, método, observaciones y detecciones (una
    plaga del catálogo u Otra con texto, con el `id` del dispositivo), o sin presencia. La
    incidencia la calcula el servidor (`ROUND_HALF_UP`, dos decimales). Lo registra quien puede
    registrar la realización. Cada detección puede traer su control (`mode: done`, con la fecha
    del monitoreo y a nombre de quien registra; o `scheduled`, que pide el permiso de programar).
    Quien no programa pide que se lo programen con `control_requested: true` (no las dos cosas):
    la detección guarda quién lo pidió y cuándo.
    Todo en una transacción. El reenvío idéntico (también con las detecciones en otro orden)
    responde `200`; otro resultado, `409 activity_already_done`. Una plaga inexistente es `400` en
    `detections`, no `404`. Evaluar **árboles** no puede pasar de los que suma la ficha de la
    parcela (`400` en `evaluated_units`); las mazorcas no tienen tope, y una parcela sin ficha o
    sin siembras no limita. `sanidad` lo pregunta por `apps/common/plot_trees.py`, que `crops`
    llena en su `ready()`, y solo lo revisa en un resultado nuevo, no en un reenvío.
  - **Controles** desde una detección (`POST /api/phytosanitary-detections/{id}/controls`): el
    control es una actividad `phytosanitary_control` y `PhytosanitaryTreatment` guarda solo el
    vínculo con la detección, qué se hizo (`method`) y el insumo previsto, que no descuenta. Uno
    realizado no puede ser futuro ni anterior al monitoreo; sus insumos se descuentan como en la
    realización. Una detección tiene varios.
  - **Historial** (`GET /api/phytosanitary-history`): los monitoreos realizados de todo lo que
    alcanza la cuenta, paginado, del más reciente al más antiguo. `farm`, `plot`, `from`, `to`,
    `pest_disease` y `other` lo acotan; una finca o parcela que no alcanza es `404`. `summary` (la
    última incidencia de cada plaga y la anterior) solo viene con `plot`, y cuenta con todas las
    páginas: comparar parcelas distintas no dice si una plaga sube o baja.
  - **Detecciones que esperan un control** (`GET /api/phytosanitary-detections/without-control`,
    solo para quien programa), sin paginar. El aviso lista solo las detecciones en que alguien **pidió** un control y nadie
    lo ha atendido: salen al programar uno o con `POST …/{id}/no-control-needed` (quien programa
    decide que no requiere control; queda quién y cuándo). "Ninguno por ahora" no avisa.
    El resumen del historial compara la última incidencia con la anterior **del mismo tipo de
    muestreo**.
  - **Evidencia** (`/api/agricultural-activities/{id}/evidence`, `/api/evidence/{id}` y
    `/api/evidence/{id}/file`): solo JPG o PNG, revisados por los primeros bytes; hasta 5 MB y 5
    por registro; solo en un monitoreo o un control realizados. Una tabla por padre
    (`PhytosanitaryMonitoringEvidence`, `PhytosanitaryTreatmentEvidence`) sobre un modelo
    abstracto. El límite del cuerpo se revisa en `initial()` de la vista, **antes de autenticar**,
    porque la revisión de CSRF lee el cuerpo. La transacción bloquea la finca, revisa y después
    guarda la foto: la subida por la red ya terminó, pero la escritura de hasta 5 MB en la base
    ocurre bajo el bloqueo (excepción conocida a "nada lento dentro de un bloqueo", aceptada
    porque el teléfono reduce la foto a unos cientos de KB). El archivo se entrega solo por la vista,
    que revisa el alcance, con `nosniff`; no hay URL pública. La elimina quien la subió, quien
    programa en la finca o el Productor, y el archivo se borra del almacenamiento con
    `transaction.on_commit`. `HealthEvidenceAuditEvent` registra quién adjuntó o eliminó cada una.
- **Notificaciones** (`apps/notifications`):
  - **Evaluación:** `python manage.py evaluate_alerts` (cada hora, como tarea programada; `--today
    AAAA-MM-DD` para probar) corre los evaluadores registrados en `apps/common/alerts.py`, guarda
    los avisos nuevos, envía las push y purga lo viejo. Un evaluador que falla no detiene a los
    demás y el comando termina con error. Cada evaluador solo calcula `NotificationDraft`; lo único
    que escribe avisos es `create_notifications` (también desde `notify()`, para una condición que
    se detecta al guardar, con `transaction.on_commit`).
  - **Sin duplicados:** única (`recipient`, `kind`, `condition_key`). `thread_key` agrupa lo de una
    misma actividad o detección: el aviso nuevo de una persona deja leídos y eliminados los
    anteriores del hilo (así el recordatorio de hoy reemplaza al de ayer). Eliminar desde la
    bandeja marca `dismissed_at` y no borra la fila: sin ella, la siguiente evaluación avisaría
    otra vez. La purga borra solo lo leído o eliminado de más de 90 días cuya condición ya pasó.
  - **Condiciones de hoy:** actividad próxima (días 2, 1 y 0, al responsable), retrasada (días 1 y
    2) y vencida (una vez, sin límite), las dos últimas al responsable y a quien programa en la
    finca; control pendiente, cada día durante los 10 primeros desde la solicitud, a quien
    programa. "Quien programa" sale de `Schedulers` (`apps/common/schedulers.py`), sin la cuenta
    técnica.
  - **Bandeja** (`/api/notifications`, `…/unread-count`, `…/{id}/read`, `…/read-all`, `DELETE
    …/{id}`, `…/{id}/restore`, `…/dismiss-read`): solo pide sesión. Cada cuenta ve sus avisos, sin
    los eliminados, y solo de lo que alcanza **hoy** con `activities.view_agriculturalactivity`
    (si le quitan una finca, los de esa finca desaparecen). Lo ajeno es `404`. Primero las
    críticas sin leer y después por fecha, con el id como desempate. `activity` usa la
    representación registrada de la actividad, la del calendario.
  - **Push** (`…/push-config`, `POST …/push-subscriptions`, `POST …/push-subscriptions/remove`):
    sin `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` y `VAPID_SUBJECT`, `public_key` es `null` y no se envía nada. El
    `endpoint` debe ser `https` de un servicio de push de navegador (Google, Mozilla, Apple o
    Microsoft, `PUSH_SERVICE_HOSTS`): el servidor le hace peticiones. Quitar un dispositivo es un
    `POST` con el `endpoint` en el cuerpo (un `DELETE` no lleva cuerpo y en la URL quedaría en los
    registros). El envío va de 6:00 a 19:00 en Bogotá, una push por persona y evaluación (o un
    resumen), sin nombres de personas, y solo de lo que la persona ve hoy en su bandeja (si ya no
    alcanza la finca, no se manda); `404`/`410` borra el dispositivo, cualquier otro error (también
    una suscripción inválida, que no detiene a los demás dispositivos) reintenta la hora siguiente,
    y una cuenta inactiva pierde sus dispositivos. `python manage.py
    generate_vapid_keys` imprime las llaves listas para las variables de entorno.
- **Los archivos subidos van a PostgreSQL** (`STORAGES["default"]` es
  `apps.common.storage.DatabaseStorage`): el disco del servidor se borra en cada despliegue. Los
  modelos usan `FileField` sin saber dónde queda el archivo; cambiar de almacenamiento es cambiar
  `STORAGES` y copiar los archivos una vez. `MEDIA_ROOT` no se usa. En las pruebas, el
  almacenamiento es el de memoria de Django y `FILE_UPLOAD_MAX_MEMORY_SIZE` sube a 10 MB (ver
  `conftest.py`).
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
- **Mostrar una cosecha:** la representación (sin su lote) vive en
  `apps/common/harvest_representation.py` porque la usan cosechas y lotes y ninguna app importa de
  la otra.
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
- **Un empleado solo alcanza las fincas en las que trabaja** (`User.farms`, una o varias) **o todas**
  (`User.all_farms`, que incluye las que se registren después). El Productor y la cuenta técnica
  alcanzan todas (`reaches_all_farms`, `apps/common/ownership.py`); un empleado sin alcance (sin
  fincas y sin la marca), ninguna: el alcance falla cerrado, y «lista vacía» nunca significa
  «todas». Empleado es la
  cuenta con productor y algún rol distinto del de Productor (`is_employee`,
  `apps/common/roles.py`). Todo lo que cuelga de una finca pasa su ruta a `owner_filter` con
  `farm=` (`"farm_id"` en una parcela, `"plot__farm_id"` en lo que cuelga de ella, `"id"` en la
  finca misma): así lo de otra finca responde `404`, igual que lo de otro productor. Un recurso
  nuevo agrega su caso a `apps/common/tests/test_farm_scope.py`. Además:
  - **El alcance de una cuenta** se envía en `farm_ids` o `all_farms` (nunca los dos) al crearla,
    al editarla o al cambiarle los roles, y es obligatorio en todo empleado, tenga o no permisos de
    campo. Las cuentas Productor y Administrador no lo llevan. La cuenta expone `farms`, `all_farms`
    y `needs_farm` (empleado sin alcance); la sesión, `farms` y `all_farms`. `GET /api/users`
    filtra por `farm` (incluye a quienes trabajan en todas) y `without_farm`. Un empleado con
    fincas solo ve a quien comparte alguna con él (o trabaja en todas); con todas, a todo el
    productor; sin alcance, solo su cuenta.
  - **El alcance que admite cada rol** (`Role.farm_scope`): `all` (la cuenta debe tener
    `all_farms`), `one` (exactamente una finca) o `many` (a elección). Capataz/Operario es `one`;
    Comercializador y Encargado de calidad, `many`; un rol propio, `many` por defecto. El rol limita
    y la cuenta tiene el valor. Dos roles que piden `all` y `one` son incompatibles
    (`role_scope_conflict`). Cambiar el alcance de un rol que ya no cumplirían sus cuentas es
    `409 role_scope_in_use`. Nadie da más alcance del que tiene: «todas» y los roles `all` solo
    los da quien alcanza todas (`farm_assignment.ensure_can_give`). Un empleado limitado crea roles
    libremente, pero edita solo los que tienen cuentas dentro de su alcance
    (`ensure_role_within_scope`, `403 role_in_use_outside_scope`).
  - **Crear empleados:** el Productor (y la cuenta técnica) en cualquier finca; un empleado de
    confianza con `accounts.users_create` solo en las suyas (la cuenta nueva toma la suya si es una
    sola; otra, o «todas», es `403`). Cambiar el alcance de alguien lo hace quien alcanza todas las
    fincas, y no se hace mientras tenga actividades programadas o retrasadas en las que deja
    (`409 account_has_pending_work`, con `pending` y `overdue`; las vencidas no bloquean; desde
    «todas», las que deja son todas las del productor fuera de la lista nueva). Cada app que asigne trabajo en una finca lo declara con
    `register_guard` (`apps/common/farm_change_guards.py`).
  - **Un empleado que registra una finca** (`farms.add_farm` en su rol) queda asignado a ella. Una
    finca con empleados asignados no se elimina (`409 farm_has_accounts`, con cuántos en `accounts`). Al eliminar un productor creado por error
    la finca se suelta de sus cuentas antes de borrarla.
  - **Insumos por finca:** el catálogo se guarda una vez por productor, pero un empleado lista,
    consulta y edita solo los que tienen una fila de existencias en su finca (también en cero o sin
    movimientos: el que él registra nace así). Esa fila sin movimientos no cuenta como registro
    (`has_records`), no sale en `GET /api/input-stocks` y se elimina con el insumo o con la finca.
    `GET /api/agricultural-inputs/catalog?search=` (`inputs.manage_inputstock`, 2 caracteres o
    más, hasta 20) busca en todo el catálogo activo sin cantidades, para traer a la finca con una
    entrada un insumo que ya usa otra. Un empleado no edita, desactiva ni elimina un insumo que
    está en más de una finca (`409 input_shared`) y nunca le cambia la unidad (`403` con
    `fields.unit`).
  - **Responsables de una actividad y recolectores de una cosecha:** la regla vive en
    `apps/common/assignable.py` y solo cambia el permiso (`activities.complete_agriculturalactivity`
    o `harvests.add_harvest`). Para una actividad: una cuenta activa con
    `activities.complete_agriculturalactivity` que trabaje en la finca de la parcela (o en todas),
    o el Productor. Al Productor solo le asigna él mismo o la cuenta técnica. Se decide por el permiso
    y no por el rol, que en un rol propio puede llamarse de cualquier forma. `GET …/assignees`
    trae `farm_ids`, `all_farms` (con la marca o el Productor, `farm_ids` va vacía) y `assignable` (relativo a quien pregunta) para que el formulario arme la lista
    de la parcela elegida, también sin conexión.
  - **Registrar la realización:** el responsable, quien tiene el permiso de programar
    (`activities.add_agriculturalactivity`) en la finca, o el Productor y la cuenta técnica
    (`ensure_can_complete`). Quien solo registra lo suyo no cierra la labor de un compañero:
    `403 permission_denied`.
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

Cada modelo del dominio tiene su admin y una prueba (`apps/common/tests/test_admin.py`) falla si
uno nuevo se queda sin él. Las reglas comunes viven en `apps/common/admin.py`:

- **Toda escritura pasa por `services`**, con `request.user` como actor, para tener las mismas
  validaciones, bloqueos, `version` y auditoría que la API. Nunca `save_model` guardando el modelo
  directo. El formulario hereda de `VersionedAdminForm` (lleva `expected_version`, y si otra persona
  cambió el registro antes, no se guarda) y el admin usa `ServiceAdminMixin`.
- **Los errores de un servicio** (`ApiError`, validaciones) se llaman con `run_service(...)`: el admin
  vuelve a la ficha del registro con el motivo como mensaje, en vez de una página de error.
- **Eliminar es por registro** (ficha del registro, confirmación estándar) y pasa por el servicio
  (`delete_farm`, `delete_plot`, `delete_input`, `delete_producer`, `delete_account`), que solo
  permite lo creado por error. Estos admins no ofrecen «Eliminar seleccionados».
- **Sin alta** de usuarios, fincas, parcelas ni insumos: llevan cosas que el admin no captura bien
  (rol, productor y activación; georreferenciación con mapa; productor dueño). Se crean desde la
  aplicación o la API.
- **Solo lectura:** `ReadOnlyAdminMixin`; con `SuperuserReadOnlyAdminMixin` además solo lo ve un
  superusuario, porque el admin no filtra por productor. Es el caso de todos los historiales,
  de las fichas con sus siembras, del inventario (existencias y movimientos) y de las actividades
  con sus insumos (`ReadOnlyInlineMixin` para lo que cuelga de su ficha). Los admins editables
  filtran por productor a quien no es la cuenta técnica (`owner_filter`).

- Usuarios, roles y eventos (autenticación y de cuentas) en `apps/accounts/admin.py`;
  productores en `apps/producers/admin.py`; fincas, parcelas, fichas, insumos y actividades, en el
  `admin.py` de cada app.
- **Usuarios:** los permisos siguen a los de la API (`users_view`, `users_update`, `users_delete`).
  Sin alta ni borrado directo. Nombres, correo y documento se guardan con `update_account`; el
  estado (`is_active`), con `set_account_status` (revoca las sesiones y protege al último
  administrador); eliminar, con `delete_account` (solo una cuenta que nunca inició sesión, por lo
  que `last_login` no se edita). Una contraseña nueva desde el admin revoca las sesiones. Los datos
  personales de una cuenta Productor van de solo lectura, como en la API. `is_staff`, `is_superuser`
  y los permisos sueltos son banderas técnicas que solo toca un superusuario. Las cuentas de
  superusuario están fuera del modelo de negocio (los servicios no las ven): se editan directo y no
  se eliminan.
- **Productores:** los permisos siguen a los de la API (`producers.view`, `producers.update`,
  `producers.change_status`, `producers.delete`), no a los que Django genera. No se puede crear
  desde el admin (el alta asigna el código de asociado y detecta el documento repetido). Se editan
  nombre, teléfono, correo, municipio y fecha de ingreso; el documento, el código y el estado no. El
  estado cambia con las acciones "Activar" y "Desactivar"; un productor creado por error se elimina
  con `delete_producer` y deja `ProducerAuditEvent`.
- **Fincas, parcelas e insumos:** se editan (incluido activar y desactivar) con `update_farm`,
  `update_plot` y `update_input`. De la finca se ve el área ya repartida en parcelas; el contorno
  de la parcela es de solo lectura (se dibuja con el mapa); la unidad de un insumo con movimientos no
  cambia. Se buscan por nombre sin tildes y por productor.
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
- **`evaluate_alerts`** (management command) es la evaluación de las alertas. En despliegue corre
  cada hora como tarea programada aparte (`5 * * * *`), con las mismas variables de entorno del
  servicio web; no corre `migrate`. Repetirla no duplica nada. **`generate_vapid_keys`** imprime un
  par de llaves de push nuevo.
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
- **Plagas y enfermedades** (`apps/health/admin.py`): con `health.manage_pestdisease`, por los
  servicios, como variedades. **Resultados de monitoreo y controles**, con sus detecciones y los
  datos de sus fotos (sin el archivo), y el **historial de la evidencia**: de solo lectura y solo
  para superusuarios. `StoredFile` no tiene admin (está en `WITHOUT_ADMIN` de `test_admin.py`):
  solo guarda bytes.

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
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | Notificaciones push, opcionales: sin las dos llaves y el `VAPID_SUBJECT` no se ofrecen (`push-config` devuelve `public_key` nulo) ni se envían. Se generan una sola vez con `python manage.py generate_vapid_keys`; si cambian, cada dispositivo debe volver a activarlas. `VAPID_SUBJECT` es un `mailto:` del equipo. En despliegue van en el servicio web y en la tarea programada |
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
    externo o generar un reporte se hace antes o después, fuera de la transacción. Excepción
    conocida: la foto de evidencia de sanidad se escribe bajo el bloqueo (la reduce el teléfono). Un archivo se
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
