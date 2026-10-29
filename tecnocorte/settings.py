import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga la configuración local sin añadir dependencias ni exponer secretos en Git.
ENV_FILE = BASE_DIR / '.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true'
_default_secret = 'tecnocorte-local-development-key-change-in-production-2026'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', _default_secret)
if not DEBUG and (not SECRET_KEY or SECRET_KEY == _default_secret):
    raise ImproperlyConfigured('DJANGO_SECRET_KEY debe configurarse con un valor secreto en producción.')
_allowed_hosts_env = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
_vercel_deployment = os.environ.get('VERCEL_URL', '').strip()
_en_vercel = bool(os.environ.get('VERCEL') or _vercel_deployment)
if not DEBUG and not _allowed_hosts_env:
    if not _en_vercel:
        raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS debe configurarse en producción.')
_hosts_base = _allowed_hosts_env or 'localhost,127.0.0.1'
ALLOWED_HOSTS = [host.strip() for host in _hosts_base.split(',') if host.strip()]
if _en_vercel:
    # Vercel usa dominios de despliegue variables y el alias .vercel.app.
    ALLOWED_HOSTS.extend(['.vercel.app'] + ([_vercel_deployment.split('/', 1)[0]] if _vercel_deployment else []))

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'sena',
    'drf_spectacular',
]

MIDDLEWARE = [
    'sena.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Aplica el modo mantenimiento configurado por el Admin (debe ir al final).
    'sena.middleware.MantenimientoMiddleware',
    # Deja la tarjeta de error amigable también en desarrollo: Django solo usa
    # sus handlers 404/403/500 cuando DEBUG está apagado.
    'sena.middleware.ErroresAmigablesMiddleware',
]

ROOT_URLCONF = 'tecnocorte.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'sena', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'sena.context_processors.carrito_contexto',
                'sena.context_processors.notificaciones_contexto',
                'sena.context_processors.formulario_contexto',
                'sena.context_processors.configuracion_contexto',
            ],
        },
    },
    {
        # Motor para las páginas de error: sin procesadores de contexto ni
        # acceso a la base de datos, para que respondan incluso cuando el
        # fallo venga de una caída de la base.
        'NAME': 'errores',
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'sena', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {'context_processors': []},
    },
]

WSGI_APPLICATION = 'tecnocorte.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'postgres'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        # El pooler en modo sesión (IPv4, compatible con PythonAnywhere) usa
        # 5432. Se puede sobrescribir con DB_PORT si el proveedor lo requiere.
        'PORT': os.environ.get('DB_PORT', '5432'),
        # Reutiliza la conexión entre peticiones para evitar el costo de reconexión por cada acción.
        # En desarrollo se cierran conexiones al terminar cada petición para
        # no agotar el pool compartido al abrir varios runserver. En producción
        # se conserva la reutilización configurable para mejorar rendimiento.
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '0' if DEBUG else '60')),
        'OPTIONS': {
            'sslmode': 'require',
            # El modo transaccional de Supavisor no soporta declaraciones preparadas
            # en el servidor; se desactiva la preparación automática del driver.
            'prepare_threshold': None,
        },
    }
}

# ── Rendimiento ─────────────────────────────────────────────────────────────
# Caché en memoria del proceso: contadores, métricas y listados con TTL corto.
# Evita repetir consultas costosas contra la BD remota (Supabase) en cada petición.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'tecnocorte-cache',
        'TIMEOUT': 300,
        'OPTIONS': {'MAX_ENTRIES': 5000},
    }
}
# La sesión se lee de la caché y se respalda en la BD: ahorra una consulta remota
# por petición sin perder persistencia entre reinicios.
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
# Los mensajes flash viajan en una cookie firmada, evitando escrituras de sesión en la BD.
MESSAGE_STORAGE = 'django.contrib.messages.storage.cookie.CookieStorage'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'sena', 'static')]
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
# Vercel es efímero: usa Cloudinary para todas las imágenes subidas.
# Se acepta CLOUDINARY_URL o las tres variables separadas.
_cloudinary_url = os.environ.get('CLOUDINARY_URL', '').strip()
_cloudinary_name = os.environ.get('CLOUDINARY_CLOUD_NAME', '').strip()
_cloudinary_key = os.environ.get('CLOUDINARY_API_KEY', '').strip()
_cloudinary_secret = os.environ.get('CLOUDINARY_API_SECRET', '').strip()
if _cloudinary_url or all((_cloudinary_name, _cloudinary_key, _cloudinary_secret)):
    if not _cloudinary_url:
        CLOUDINARY_STORAGE = {
            'CLOUD_NAME': _cloudinary_name,
            'API_KEY': _cloudinary_key,
            'API_SECRET': _cloudinary_secret,
            'SECURE': True,
        }
    STORAGES = {
        'default': {'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
LOGIN_URL = 'sena:login'

# En desarrollo los correos se muestran en la consola. En producción se activa
# SMTP mediante variables de entorno, sin guardar credenciales en el proyecto.
_email_backend_configurado = os.environ.get('EMAIL_BACKEND', '').strip()
# Si no se especifica un backend, el desarrollo imprime los correos en consola
# y producción usa SMTP. Si se especifica, se respeta para permitir servicios
# externos como SendGrid, Mailgun o Gmail.
EMAIL_BACKEND = _email_backend_configurado or (
    'django.core.mail.backends.console.EmailBackend'
    if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '10'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
# Gmail muestra las contraseñas de aplicación agrupadas con espacios; al
# copiarlas a PythonAnywhere esos espacios pueden provocar un error SMTP 535.
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '').replace(' ', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'notificaciones@tecnocorte.local')
CONTACT_EMAIL = os.environ.get('CONTACT_EMAIL', 'tecnocorte083@gmail.com')
# URL pública opcional usada por los enlaces de correos enviados por comandos
# programados, que no tienen un objeto request disponible.
SITE_URL = os.environ.get('SITE_URL', '').rstrip('/')
if not SITE_URL and _vercel_deployment:
    SITE_URL = f'https://{_vercel_deployment}'
# Desactivado temporalmente: las cuentas no requieren código para iniciar sesión.
# La implementación queda disponible para activarla más adelante de forma controlada.
REQUIRE_EMAIL_VERIFICATION = True
EMAIL_VERIFICATION_MINUTES = 15
EMAIL_VERIFICATION_RESEND_SECONDS = int(os.environ.get('EMAIL_VERIFICATION_RESEND_SECONDS', '60'))
BACKUP_EMAIL = os.environ.get('BACKUP_EMAIL', CONTACT_EMAIL)
BACKUP_MAX_ATTACHMENT_BYTES = int(os.environ.get('BACKUP_MAX_ATTACHMENT_BYTES', str(20 * 1024 * 1024)))
BACKUP_ENCRYPTION_KEY = os.environ.get('BACKUP_ENCRYPTION_KEY', '')
JWT_ACCESS_MINUTES = int(os.environ.get('JWT_ACCESS_MINUTES', '15'))
JWT_REFRESH_DAYS = int(os.environ.get('JWT_REFRESH_DAYS', '7'))

SESSION_COOKIE_SECURE = not DEBUG #Cuando inicias sesión, el sistema te da un "carnet".
CSRF_COOKIE_SECURE = not DEBUG #Es una marca de agua que confirma que un formulario realmente lo llenaste tú y no un virus.
SESSION_COOKIE_AGE = int(os.environ.get('DJANGO_SESSION_AGE', str(60 * 60 * 8)))
SESSION_SAVE_EVERY_REQUEST = True
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SSL_REDIRECT', 'True' if not DEBUG else 'False').lower() == 'true' #Si un usuario intenta entrar por la puerta transparente (http://) esta regla lo agarra de la mano y lo manda automáticamente al túnel seguro (https://).
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '31536000' if not DEBUG else '0')) #Le dice al navegador de la persona: "Memoriza esto: por los próximos X segundos, ni se te ocurra intentar entrar por la puerta transparente, entra siempre por el túnel seguro.
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get('DJANGO_HSTS_INCLUDE_SUBDOMAINS', 'True' if not DEBUG else 'False').lower() == 'true'
SECURE_HSTS_PRELOAD = os.environ.get('DJANGO_HSTS_PRELOAD', 'True' if not DEBUG else 'False').lower() == 'true'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
_csrf_origins = [origin.strip() for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]
if _en_vercel:
    _csrf_origins.extend(['https://*.vercel.app'])
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(_csrf_origins))
if os.environ.get('DJANGO_USE_PROXY_SSL', 'False').lower() == 'true' or _en_vercel:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated'
    ],
    # Límite de peticiones para frenar abusos (spam)
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle', #Controla el tráfico de usuarios no autenticados
        'rest_framework.throttling.UserRateThrottle', #Controla el tráfico de usuarios autenticados
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day', # Límite para usuarios no autenticados
        'user': '1000/day', # Límite para usuarios autenticados
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}


SPECTACULAR_SETTINGS = {
    "TITLE": "TecnoCorte API",
    "DESCRIPTION": "Documentación de la API de TecnoCorte (usuarios, peluquerías, productos y reservas).",
    "VERSION": "1.0.0",
}
