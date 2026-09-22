import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga la configuración local sin añadir dependencias ni exponer secretos en Git.
ENV_FILE = BASE_DIR / '.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'tecnocorte-local-development-key-change-in-production-2026')
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'
ALLOWED_HOSTS = [host.strip() for host in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]

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
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'tecnocorte.urls'

TEMPLATES = [{
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
        ],
    },
}]

WSGI_APPLICATION = 'tecnocorte.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'postgres'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': os.environ.get('DB_PORT', '6543'),
        # Reutiliza la conexión entre peticiones para evitar el costo de reconexión por cada acción.
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
        'OPTIONS': {
            'sslmode': 'require',
            # El modo transaccional de Supavisor no soporta declaraciones preparadas
            # en el servidor; se desactiva la preparación automática del driver.
            'prepare_threshold': None,
        },
    }
}

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
LOGIN_URL = 'sena:login'

# En desarrollo los correos se muestran en la consola. En producción se activa
# SMTP mediante variables de entorno, sin guardar credenciales en el proyecto.
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'notificaciones@tecnocorte.local')
CONTACT_EMAIL = os.environ.get('CONTACT_EMAIL', 'tecnocorte083@gmail.com')

SESSION_COOKIE_SECURE = not DEBUG #Cuando inicias sesión, el sistema te da un "carnet".
CSRF_COOKIE_SECURE = not DEBUG #Es una marca de agua que confirma que un formulario realmente lo llenaste tú y no un virus.
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SSL_REDIRECT', 'False').lower() == 'true' #Si un usuario intenta entrar por la puerta transparente (http://) esta regla lo agarra de la mano y lo manda automáticamente al túnel seguro (https://).
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '0')) #Le dice al navegador de la persona: "Memoriza esto: por los próximos X segundos, ni se te ocurra intentar entrar por la puerta transparente, entra siempre por el túnel seguro.

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
    "TITLE": "Mi API",
    "DESCRIPTION": "Documentación de la API",
    "VERSION": "1.0.0",
}
