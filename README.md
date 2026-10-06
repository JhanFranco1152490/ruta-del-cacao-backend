# Ruta del Cacao — Backend

API **Django** del sistema de trazabilidad de la producción de cacao en Norte de Santander
(proyecto académico UFPS). La consume la aplicación Next.js del repo hermano
`ruta-del-cacao-frontend`. Las reglas de trabajo, el contrato de la API y las decisiones de
diseño están en [`AGENTS.md`](AGENTS.md); este archivo es la entrada rápida.

## Qué hace hoy (primer sprint)

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
parcelas dibujadas y fichas productivas, y deja dos cuentas para entrar:

| Cuenta | Correo | Contraseña |
| --- | --- | --- |
| Administrador de la asociación | `administrador@example.com` | `CacaoDemo2026` |
| Productor (Carlos Andrés Rincón Peña) | `productor@example.com` | `CacaoDemo2026` |

- Pasa por los mismos servicios que la API, así que respeta sus reglas y deja historial.
- **Se puede repetir:** no duplica nada, no toca un productor que ya existe (aunque se haya
  editado desde la aplicación) y vuelve a activar las dos cuentas con su contraseña, por si
  alguien la cambió o las desactivó.
- No envía correos: las demás cuentas de productor quedan pendientes de activación.
- La contraseña es pública (la muestra la pantalla de inicio de sesión): **no se corre en un
  despliegue con datos reales.**

En un despliegue, se corre una vez desde la consola del servicio, después de las migraciones.

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

Las pruebas necesitan el PostgreSQL del `.env` (crean y borran su propia base `test_*`).

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
- Las dos son entornos distintos, con su propia base de datos: la semilla de demostración se corre
  en cada uno por separado.

## Despliegue

El `Procfile` corre `migrate`, `flushexpiredtokens` y `collectstatic` antes de levantar
`gunicorn`. Toda la configuración sale de variables de entorno; en despliegue, `DEBUG=False`.
