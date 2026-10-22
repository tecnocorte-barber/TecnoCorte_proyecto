# TecnoCorte

Aplicación Django para gestionar barberías, reservas, productos y pedidos.

## Ejecutar en local

El proyecto usa SQLite por defecto en desarrollo, por lo que no necesita
PostgreSQL para arrancar.

```bash
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Abrir <http://127.0.0.1:8000/>.

Para crear un usuario administrador:

```bash
python manage.py createsuperuser
```

El archivo `.env` es local y no debe compartirse. Se puede copiar
`.env.example` como base para configurar otro entorno.

El registro exige verificar el correo antes de crear la cuenta. En producción
configura `SITE_URL` con el dominio público exacto (incluyendo `https://`) para
que los enlaces de verificación funcionen aunque el servidor use un proxy o
cambie el host interno:

```env
SITE_URL=https://tu-dominio-publico.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
```

## Comandos útiles

```bash
python manage.py check
python manage.py test
python manage.py collectstatic --noinput
```

## Producción

El servidor WSGI usa `tecnocorte.settings`, que espera PostgreSQL y las
variables `DB_*`. Para ejecutar comandos administrativos contra producción:

```bash
DJANGO_SETTINGS_MODULE=tecnocorte.settings python manage.py check --deploy
```

No se debe cambiar el `DJANGO_SETTINGS_MODULE` global del entorno local: el
`manage.py` ya selecciona `tecnocorte.settings_local` automáticamente.
