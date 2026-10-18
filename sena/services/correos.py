"""Servicio único de correo transaccional de TecnoCorte."""

import logging
import os
from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def enviar_correo(usuario, asunto, cuerpo, request=None, enlace=None, texto_enlace=None):
    """Envía un correo HTML a un usuario registrado."""
    if not usuario or not usuario.email:
        return False
    return enviar_correo_destino(usuario.email, asunto, cuerpo, request=request, enlace=enlace, texto_enlace=texto_enlace)


def enviar_correo_destino(destinatario, asunto, cuerpo, request=None, enlace=None, texto_enlace=None):
    """Envía correo texto/HTML con el logo embebido y registra fallos SMTP."""
    if not destinatario:
        return False
    html = render_to_string("emails/notificacion.html", {
        "asunto": asunto, "cuerpo": cuerpo, "enlace": enlace,
        "texto_enlace": texto_enlace or "Ver en TecnoCorte",
        "logo_url": "cid:tecnocorte-logo",
    })
    correo = EmailMultiAlternatives(asunto, cuerpo, settings.DEFAULT_FROM_EMAIL, [destinatario])
    correo.attach_alternative(html, "text/html")
    logo_path = os.path.join(settings.BASE_DIR, "sena", "static", "sena", "images", "Logo.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as archivo_logo:
            imagen = MIMEImage(archivo_logo.read(), _subtype="png")
        imagen.add_header("Content-ID", "<tecnocorte-logo>")
        imagen.add_header("Content-Disposition", "inline", filename="Logo.png")
        correo.attach(imagen)
    try:
        return bool(correo.send(fail_silently=False))
    except Exception:
        logger.exception("No se pudo enviar correo a %s con asunto %s", destinatario, asunto)
        return False


def enviar_correo_cita(request, usuario, asunto, cuerpo, enlace=None):
    """Atajo para los correos relacionados con una reserva."""
    return enviar_correo(usuario, asunto, cuerpo, request=request, enlace=enlace, texto_enlace="Revisar mi cita" if enlace else None)
