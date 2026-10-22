# Ruta del Cacao — Backend

API **Django** del sistema de trazabilidad de la producción de cacao en Norte de Santander
(proyecto académico UFPS). La consume la aplicación Next.js del repo hermano
`ruta-del-cacao-frontend`. Las reglas de trabajo, el contrato de la API y las decisiones de
diseño están en [`AGENTS.md`](AGENTS.md); este archivo es la entrada rápida.

## Qué hace hoy

### Sprint 2 (05/10 – 22/10/2026)

| App | Qué cubre |
| --- | --- |
| `inputs` | Catálogo de insumos de cada productor y su inventario por finca: existencias y movimientos de entrada, conteo y salida, con su historial |
| `activities` | Actividades agrícolas de cada parcela: programar, reprogramar, registrar la realización (con los insumos que gastó) y consultar por periodo; retrasada y vencida salen de la fecha |
| `health` | Sanidad: catálogo de plagas y enfermedades, el resultado de un monitoreo con sus detecciones e incidencia, controles fitosanitarios, historial, detecciones que esperan control y fotos de evidencia |
| `notifications` | Avisos de cada persona (actividad próxima, retrasada o vencida; control pendiente), bandeja y notificaciones push |
| `harvests` | Cosechas: una recolección por parcela y fecha, con su peso en verde, su variedad y su recolector |
| `lots` | Lotes con su código de trazabilidad (`000123-F02-P05-261014-1`) y la cadena de estados que fermentación y secado usarán |
| `facilities` | Cajones de fermentación y marquesinas de secado de cada finca, con su capacidad y su estado |

Además: **alcance por finca** (un empleado solo alcanza las fincas en las que trabaja, o todas),
`apps/common/contracts/` (lo que una app ofrece a las demás sin importarlas), el comando
`evaluate_alerts` y una **semilla de demostración** mucho más completa (ver abajo).

### Sprint 1 (14/09 – 04/10/2026)

| App | Qué cubre |
| --- | --- |
| `accounts` | Cuentas por correo, sesión en cookies `HttpOnly` con JWT, activación y recuperación de contraseña por correo, bloqueo por intentos, roles del sistema y roles propios con permisos delegables |
| `producers` | Expediente del productor con código de asociado, búsqueda sin tildes, estado y eliminación de uno creado por error |
| `farms` | Fincas con ubicación en Norte de Santander, altitud validada por municipio, conteos y puntos del mapa, y su historial |
| `plots` | Parcelas con contorno opcional, área calculada, reglas de área disponible, superposición y distancia a la finca, y su historial |
| `crops` | Catálogo de variedades de cacao (cargado desde AGROSAVIA) y ficha productiva de cada parcela con sus siembras e historial de versiones |
| `demo_data` | Comando que carga datos de demostración (ver abajo) |

Fincas, parcelas y fichas aceptan registros creados sin conexión en el dispositivo: reenviar el
mismo registro nunca lo duplica.

## Puesta en marcha

Requiere Python 3.12 y PostgreSQL.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
cp .env.example .env              # credenciales de tu PostgreSQL local
python manage.py migrate
python manage.py seed_demo_data   # opcional: datos y cuentas de demostración
python manage.py runserver
```

Con `DEBUG=True` el esquema OpenAPI queda en `/api/schema` y Swagger en `/api/docs`. Las
variables de entorno están descritas en `AGENTS.md` y listadas en `.env.example`.

## Datos de demostración

`python manage.py seed_demo_data` carga cinco productores inventados (uno inactivo) con fincas,
parcelas dibujadas y fichas productivas, deja cuatro cuentas para entrar y llena **La Esperanza**, la
finca del productor de demostración:

| Cuenta | Correo | Contraseña |
| --- | --- | --- |
| Administrador de la asociación | `administrador@example.com` | `CacaoDemo2026` |
| Productor (Carlos Andrés Rincón Peña) | `productor@example.com` | `CacaoDemo2026` |
| Capataz de La Esperanza | `capataz@example.com` | `CacaoDemo2026` |
| Operario de El Mirador | `operario@example.com` | `CacaoDemo2026` |

En La Esperanza deja insumos con existencias, cajones y una marquesina, labores en todos sus
estados (programadas, una retrasada, una vencida y realizadas con insumos descontados), monitoreos
del pasado (con una monilia atendida y una mazorca negra esperando control, y uno sin presencia),
tres cosechas, dos lotes y los avisos de la campana; y deja listo lo que piden las demostraciones en
vivo (dos monitoreos programados para hoy, una variedad sembrada y el nombre `CF-01` libre).

- Pasa por los mismos servicios que la API, así que respeta sus reglas y deja historial. Lo que los
  servicios no dejan crear en el pasado se crea hoy y se corre a su fecha.
- **Se puede repetir:** completa solo lo que falta, no toca un productor que ya existe (aunque se
  haya editado desde la aplicación), restablece las cuentas con su contraseña, vuelve a programar los
  monitoreos de hoy si ya se registraron y elimina un `CF-01` de un ensayo anterior.
- No envía correos: las demás cuentas de productor quedan pendientes de activación.
- La contraseña es pública (la muestra la pantalla de inicio de sesión): **no se corre en un
  despliegue con datos reales.**

En un despliegue, se corre una vez desde la consola del servicio, después de las migraciones.

## Tareas programadas y notificaciones

- **`python manage.py evaluate_alerts`** revisa las condiciones de aviso y guarda las notificaciones
  nuevas. En despliegue corre **cada hora** como un servicio cron aparte (`5 * * * *`), con las
  mismas variables de entorno del servicio web; no corre `migrate`. Repetirlo no duplica nada.
  `--today AAAA-MM-DD` evalúa como si fuera ese día, para probar.
- **Notificaciones push:** `python manage.py generate_vapid_keys` imprime las llaves; con
  `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` y `VAPID_SUBJECT` en el servicio web y en el cron se
  ofrecen y se envían. Sin ellas, no. Se prueban con la app instalada y con HTTPS.

## Correo (Resend) y spam

La activación de una cuenta y la recuperación de contraseña salen por correo. **Pueden llegar a la
carpeta de spam**, en especial a buzones institucionales: pide a quien lo espera que la revise y
lo marque como "no es spam". Para reducirlo, el dominio de envío debe tener SPF, DKIM y DMARC
verificados, `DEFAULT_FROM_EMAIL` debe ser una dirección de ese dominio y el rastreo de clics y
aperturas debe estar apagado en Resend. El detalle está en `AGENTS.md`, sección "Si el correo
llega a spam". Las cuentas de demostración no necesitan correo.

## Pruebas y verificación

```bash
pytest --cov -q
ruff check .
black --check .
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml
```

Las pruebas necesitan el PostgreSQL del `.env` (crean y borran su propia base `test_*`): **no corras
dos veces `pytest` a la vez**, porque se la borran entre sí. La suite completa tarda unos 35 a 40
minutos; al cerrar el sprint 2 pasó con 3144 pruebas en verde.

## Entornos

| Entorno | Rama | API | Aplicación que la usa |
| --- | --- | --- | --- |
| Producción | `main` | https://api-rutadelcacao.escapate.tours/ | https://rutadelcacao.escapate.tours/ |
| Staging | `dev` | https://api-staging-rutadelcacao.escapate.tours/ | https://staging-rutadelcacao.escapate.tours/ |

Cada API sirve a la aplicación de su mismo entorno, y por eso en cada una:

- `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS` y `CSRF_TRUSTED_ORIGINS` son la dirección de **esa**
  aplicación (sin barra final en los dos últimos); `FRONTEND_URL` arma los enlaces de los correos
  de activación y de recuperación.
- `ALLOWED_HOSTS` incluye el dominio de la API.
- La sesión viaja en cookies `SameSite=Lax`, que exigen que la aplicación y la API estén en el
  mismo sitio: ambas viven bajo `escapate.tours`.
- La semilla de demostración se corre en cada entorno donde se quiera tener esos datos; no se
  comparte entre ellos.

## Despliegue

El `Procfile` corre `migrate`, `flushexpiredtokens` y `collectstatic` antes de levantar
`gunicorn`. Toda la configuración sale de variables de entorno; en despliegue, `DEBUG=False`.

**Al pasar el sprint 2 a un entorno:** `migrate` (los empleados que ya existían quedan sin alcance
salvo los de rol de una sola finca cuando el productor solo tiene una; los roles ya sembrados pierden
un permiso; se numeran las fincas y parcelas existentes), crear el servicio cron de `evaluate_alerts`,
generar las llaves VAPID y configurarlas, y probar una notificación push real en Android y en iPhone
con la app instalada.
