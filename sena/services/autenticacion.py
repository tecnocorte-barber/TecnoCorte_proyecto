"""Servicios de autenticación reutilizables por las vistas web y la API."""
import hashlib
import hmac
import secrets
from urllib.parse import urljoin
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.signing import salted_hmac
from django.utils import timezone

from ..models import RegistroPendiente, Usuario
from .correos import enviar_correo, enviar_correo_destino


def url_publica(request, ruta):
    """Construye enlaces estables detrás de Render, Vercel o PythonAnywhere."""
    base = (getattr(settings, "SITE_URL", "") or "").strip().rstrip("/")
    if base:
        return urljoin(base + "/", ruta.lstrip("/"))
    return request.build_absolute_uri(ruta)

RESET_SALT = "tecnocorte-password-reset"


def token_recuperacion(usuario):
    version = salted_hmac(RESET_SALT, usuario.password).hexdigest()
    return signing.dumps({"id": usuario.id, "version": version}, salt=RESET_SALT, compress=True)


def usuario_desde_token(token):
    try:
        datos = signing.loads(token, salt=RESET_SALT, max_age=3600)
    except (signing.BadSignature, signing.SignatureExpired, TypeError, ValueError):
        return None
    usuario = Usuario.objects.filter(id=datos.get("id"), activo=True).first()
    if not usuario:
        return None
    version_actual = salted_hmac(RESET_SALT, usuario.password).hexdigest()
    return usuario if hmac.compare_digest(datos.get("version", ""), version_actual) else None


def crear_codigo_verificacion(registro):
    """Genera un código nuevo para un registro pendiente y devuelve el código."""
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    registro.codigo_hash = hashlib.sha256(codigo.encode()).hexdigest()
    registro.codigo_expira = timezone.now() + timedelta(
        minutes=settings.EMAIL_VERIFICATION_MINUTES
    )
    token = secrets.token_urlsafe(48)
    registro.token_hash = hashlib.sha256(token.encode()).hexdigest()
    registro.token_expira = timezone.now() + timedelta(hours=24)
    registro.ultimo_envio = timezone.now()
    registro.save(update_fields=["codigo_hash", "codigo_expira", "token_hash", "token_expira", "ultimo_envio", "actualizado"])
    return codigo, token


def crear_token_verificacion(registro):
    """Devuelve un token de enlace y lo deja almacenado solo como hash."""
    token = secrets.token_urlsafe(48)
    registro.token_hash = hashlib.sha256(token.encode()).hexdigest()
    registro.token_expira = timezone.now() + timedelta(hours=24)
    registro.save(update_fields=["token_hash", "token_expira", "actualizado"])
    return token


def enviar_codigo_verificacion(request, registro, enlace):
    codigo, token = crear_codigo_verificacion(registro)
    if callable(enlace):
        enlace = enlace(token)
    enviado = enviar_correo_destino(
        registro.email,
        "Verifica tu correo de TecnoCorte",
        f"Hola {registro.nombre},\n\nTu código de verificación es: {codigo}\n\n"
        f"Este código vence en {settings.EMAIL_VERIFICATION_MINUTES} minutos y solo puede usarse una vez.\n\n"
        "Si prefieres, también puedes usar el botón del correo para verificar tu cuenta directamente.",
        request=request,
        enlace=enlace,
        texto_enlace="Verificar mi correo",
    )
    return enviado, token


def reenvio_permitido(request, usuario):
    clave = f"verificacion_reenvio_{usuario.email}_{request.META.get('REMOTE_ADDR', '')}"
    if cache.get(clave):
        return False
    cache.set(clave, True, settings.EMAIL_VERIFICATION_RESEND_SECONDS)
    return True
