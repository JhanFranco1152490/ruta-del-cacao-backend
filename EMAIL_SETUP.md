# Recuperación de contraseña por correo

El backend expone estos endpoints (requieren cookie y cabecera CSRF):

- `GET /api/auth/csrf`: obtiene la cookie y el token CSRF.
- `POST /api/auth/password-reset/request`, con `{"email":"productor@example.com"}`:
  envía un enlace si la cuenta está activa. Responde `202` con un mensaje genérico.
- `POST /api/auth/password-reset/confirm`, con `uid`, `token`, `new_password` y
  `new_password_confirmation`: cambia la contraseña y revoca las sesiones anteriores.
  Responde `204` cuando termina correctamente.

El enlace apunta a `FRONTEND_URL/restablecer-contrasena?uid=...&token=...`, vence
en 30 minutos y es de un solo uso. El formulario del frontend debe enviar `uid`,
`token` y las dos contraseñas al endpoint de confirmación. La contraseña debe
tener entre 8 y 50 caracteres y cumplir los validadores configurados en Django.

## Configurar Gmail

1. Activa la verificación en dos pasos de la cuenta remitente.
2. Crea una [contraseña de aplicación](https://myaccount.google.com/apppasswords).
   Google explica los requisitos y las restricciones de disponibilidad en su
   [ayuda de contraseñas de aplicación](https://support.google.com/accounts/answer/185833?hl=es).
3. Completa estas variables en `config/.env` (o en las variables del despliegue):

   ```dotenv
   MAILER_BACKEND=django.core.mail.backends.smtp.EmailBackend
   MAILER_HOST=smtp.gmail.com
   MAILER_PORT=587
   MAILER_USERNAME=tu-cuenta@gmail.com
   MAILER_PASSWORD=tu-contraseña-de-aplicación
   MAILER_USE_TLS=True
   DEFAULT_FROM_EMAIL=tu-cuenta@gmail.com
   FRONTEND_URL=http://localhost:3000
   ```

4. Reinicia el backend. En producción, usa la URL HTTPS real del frontend.
5. Solicita la recuperación para una cuenta activa registrada y revisa su bandeja
   de entrada y spam. Abre el enlace, cambia la contraseña y comprueba que puedes
   iniciar sesión con la nueva contraseña.

No guardes credenciales reales en archivos versionados. Los parámetros de Gmail
se pueden consultar en la [documentación de Google](https://support.google.com/mail/answer/7104828?hl=es).

Con `django.core.mail.backends.console.EmailBackend`, el correo se imprime en la
terminal del backend y no llega a ninguna bandeja de entrada. Las pruebas de API
usan el buzón en memoria de Django y no verifican la entrega real por Gmail.
