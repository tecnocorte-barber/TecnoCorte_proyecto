"""Servicios de autenticación reutilizables por las vistas web y la API."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.signing import salted_hmac
from django.utils import timezone

from ..models import Usuario
from .correos import enviar_correo

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


def crear_codigo_verificacion(usuario):
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    usuario.codigo_verificacion_hash = hashlib.sha256(codigo.encode()).hexdigest()
    usuario.codigo_verificacion_expira = timezone.now() + timedelta(
        minutes=settings.EMAIL_VERIFICATION_MINUTES
    )
    usuario.save(update_fields=["codigo_verificacion_hash", "codigo_verificacion_expira"])
    return codigo


def enviar_codigo_verificacion(request, usuario):
    codigo = crear_codigo_verificacion(usuario)
    return enviar_correo(
        usuario,
        "Verifica tu correo de TecnoCorte",
        f"Hola {usuario.nombre},\n\nTu código de verificación es: {codigo}\n\n"
        f"Este código vence en {settings.EMAIL_VERIFICATION_MINUTES} minutos y solo puede usarse una vez.",
        request=request,
    )


def reenvio_permitido(request, usuario):
    clave = f"verificacion_reenvio_{usuario.id}_{request.META.get('REMOTE_ADDR', '')}"
    if cache.get(clave):
        return False
    cache.set(clave, True, settings.EMAIL_VERIFICATION_RESEND_SECONDS)
    return True
