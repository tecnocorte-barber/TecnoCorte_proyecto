# Variables para Vercel

En Vercel entra a **Settings → Environment Variables** y agrega estas variables
para **Production**. Para Preview puedes repetirlas con valores de prueba.

## Django

```text
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<generar-una-clave-secreta-larga>
DJANGO_ALLOWED_HOSTS=tecno-corte-proyecto.vercel.app,.vercel.app
DJANGO_CSRF_TRUSTED_ORIGINS=https://tecno-corte-proyecto.vercel.app
DJANGO_USE_PROXY_SSL=True
DJANGO_SSL_REDIRECT=True
DJANGO_HSTS_SECONDS=31536000
```

`VERCEL_URL` la agrega Vercel automáticamente. `SITE_URL` es opcional.

## PostgreSQL

```text
DB_NAME=postgres
DB_USER=<usuario-postgres>
DB_PASSWORD=<contraseña-postgres>
DB_HOST=<host-postgres>
DB_PORT=5432
DB_CONN_MAX_AGE=0
```

## Correo

```text
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<correo-smtp>
EMAIL_HOST_PASSWORD=<contraseña-de-aplicacion>
DEFAULT_FROM_EMAIL=<correo-smtp>
CONTACT_EMAIL=<correo-de-contacto>
```

## Backups y JWT

```text
BACKUP_EMAIL=<correo-para-backups>
BACKUP_MAX_ATTACHMENT_BYTES=20971520
BACKUP_ENCRYPTION_KEY=<clave-fernet>
JWT_ACCESS_MINUTES=15
JWT_REFRESH_DAYS=7
```

No subas el archivo `.env` al repositorio ni pegues valores reales en este
archivo de documentación. Después de guardar las variables, ejecuta un nuevo
Redeploy en Vercel.
