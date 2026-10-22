# Registro y aviso de errores inesperados.
#
# Cuando algo falla, la persona que navega solo ve una página amigable con un
# código corto. El detalle completo queda aquí, en RegistroError, y los
# administradores reciben una notificación, un mensaje de contacto y un correo.
#
# Todo lo que toca la base de datos o el correo va envuelto en try/except: si se
# cayó la BD, el aviso no puede empeorar la caída.
import logging
import secrets
import sys
import threading
import traceback

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.signals import got_request_exception
from django.http import (
    Http404,
    HttpResponseForbidden,
    HttpResponseNotFound,
    HttpResponseServerError,
)
from django.shortcuts import render
from django.utils import timezone

from .models import Notificacion, RegistroError, Usuario

logger = logging.getLogger("sena.errores")

# Longitudes máximas para no guardar basura en la BD.
LARGO_MENSAJE = 4000
LARGO_DETALLE = 20000


def _codigo_corto():
    """Código tipo 'K7F2QX' que se le puede pedir a la persona por teléfono."""
    return "E-" + secrets.token_hex(3).upper()


def _ip_de(request):
    """IP real del cliente, contemplando proxies (Render/Supabase ponen X-Forwarded-For)."""
    if request is None:
        return ""
    cabecera = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if cabecera:
        return cabecera.split(",")[0].strip()[:45]
    return (request.META.get("REMOTE_ADDR") or "")[:45]


def _usuario_de(request):
    if request is None:
        return None
    usuario_id = (request.session.get("logueado") or {}).get("id")
    if not usuario_id:
        return None
    return Usuario.objects.filter(id=usuario_id).only("id").first()


def registrar_error(request, excepcion, codigo_http):
    """Guarda el error, avisa a los Admin si procede y devuelve el código corto.

    Solo los fallos 5xx se notifican: avisar también por cada 404 inundaría al
    Admin, porque los rastreadores generan enlaces inexistentes sin parar.
    Los 4xx quedan igualmente registrados y en el log.

    Devuelve una cadena siempre; nunca lanza excepción.
    """
    codigo = _codigo_corto()
    if isinstance(excepcion, Exception):
        tipo = excepcion.__class__.__name__
        mensaje = str(excepcion)[:LARGO_MENSAJE]
        traza = "".join(traceback.format_exception(excepcion))[:LARGO_DETALLE]
    else:
        tipo = type(excepcion).__name__
        mensaje = str(excepcion)[:LARGO_MENSAJE]
        traza = ""

    registro = None
    try:
        registro = RegistroError.objects.create(
            codigo=codigo,
            codigo_http=codigo_http,
            ruta=(request.path_info if request else "/")[:300],
            metodo=(request.method if request else "")[:10],
            tipo=tipo,
            mensaje=mensaje,
            detalle=traza,
            usuario=_usuario_de(request),
            ip=_ip_de(request),
            navegador=(request.META.get("HTTP_USER_AGENT", "") if request else "")[:200],
        )
    except Exception:
        # Sin registro persistido el sitio sigue funcionando; el detalle queda en el log.
        logger.error("No se pudo guardar RegistroError: %s", codigo, exc_info=True)

    # El log siempre recibe la traza completa, haya o no base de datos.
    if codigo_http >= 500:
        logger.error("Error %s [%s] %s %s", codigo_http, codigo,
                     request.path_info if request else "/", traza)
    else:
        logger.warning("Aviso %s [%s] %s %s: %s", codigo_http, codigo,
                       request.method if request else "", request.path_info if request else "/", tipo)

    # Solo los 5xx se notifican: un 404 no debe inundar al Admin.
    if codigo_http >= 500:
        _avisar_admins(request, registro, codigo, tipo, mensaje, codigo_http)
    return codigo


def _avisar_admins(request, registro, codigo, tipo, mensaje, codigo_http):
    """Notificación + mensaje de contacto + correo para los administradores.

    Se usa solo con fallos 5xx; los 4xx no generan avisos.
    """
    titulo = registro.titulo if registro else "Error inesperado"
    resumen = f"{titulo} [{codigo}]: {tipo} en {(registro.ruta if registro else '/')}"
    notificado = False

    # 1. Notificación dentro del panel (aparece en la campana del Admin).
    try:
        admins = list(Usuario.objects.filter(rol="Admin", activo=True).only("id"))
        if admins:
            Notificacion.objects.bulk_create(
                [Notificacion(usuario=admin, mensaje=resumen[:255]) for admin in admins]
            )
            notificado = True
    except Exception:
        logger.error("No se pudieron crear las notificaciones de error [%s]", codigo, exc_info=True)

    # 2. Correo al contacto oficial del sitio.
    try:
        send_mail(
            subject=f"[TecnoCorte] {titulo} [{codigo}]",
            message=(
                f"{titulo}\n\n"
                f"Código: {codigo}\n"
                f"Estado HTTP: {codigo_http}\n"
                f"Ruta: {(registro.ruta if registro else '/')} ({(registro.metodo if registro else '')})\n"
                f"Error: {tipo}: {mensaje}\n"
                f"Persona: {(registro.usuario.email if registro and registro.usuario else 'sin sesión')}\n"
                f"IP: {(registro.ip if registro else '')}\n\n"
                "La traza completa está en el administrador de Django,\n"
                "sección Registros de error."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.CONTACT_EMAIL],
            fail_silently=True,
        )
    except Exception:
        logger.error("No se pudo enviar el correo de error [%s]", codigo, exc_info=True)

    if registro is not None and notificado:
        RegistroError.objects.filter(pk=registro.pk).update(notificado=True)


# ── Captura de la traza para el handler de 500 ──────────────────────────────
# Django llama a handler500 pasándole solo la petición, así que la excepción
# hay que recuperarla de la señal got_request_exception, que se emite justo
# antes de resolver el error. Se guarda en un hilo para no mezclar peticiones
# concurrentes.
_hilo = threading.local()


def capturar_excepcion(sender=None, request=None, **kwargs):
    """Receiver de got_request_exception: guarda la traza del fallo actual."""
    _hilo.exc_info = sys.exc_info()


def ultima_excepcion():
    """Devuelve la última traza capturada en este hilo y la limpia."""
    traza = getattr(_hilo, "exc_info", None)
    if hasattr(_hilo, "exc_info"):
        del _hilo.exc_info
    return traza


# Se conecta al importar el módulo. SenaConfig.ready() asegura que esto pase
# antes de la primera petición, aunque el handler500 no se haya usado nunca.
if not any(
    receiver is capturar_excepcion
    for receiver, _ in got_request_exception.receivers
):
    got_request_exception.connect(capturar_excepcion, dispatch_uid="sena.errores.traza")


# ── Tarjeta amigable (handlers de Django y middleware de errores) ───────────
PLANTILLA_ERROR = "errores/error.html"

# Marca que la tarjeta amigable deja en la respuesta. Evita que el middleware
# vuelva a registrarla creyendo que es una página de error sin tratar.
MARCA_AMIGABLE = "_tc_tarjeta_amigable"

# Rutas de sondas automáticas que no pertenecen a TecnoCorte. Se responden con
# 404, pero no se guardan como errores para no llenar el panel del Admin.
RUTAS_404_RUIDO = {"/v1/models", "/api"}

# Todas las tarjetas dicen lo mismo: hubo un fallo y el equipo ya fue avisado.
# El 403 se mantiene aparte porque no es un fallo del sitio, sino una sección
# sin permisos (el decorador de roles redirige al login, así que es raro verlo).
_TITULOS = {
    403: "No tienes permiso para ver esta página",
}


def es_amigable(respuesta):
    """True si la respuesta ya es la tarjeta amigable."""
    return bool(getattr(respuesta, MARCA_AMIGABLE, False))


def es_admin(request):
    """True solo si quien navega trae sesión de administrador.

    Se lee de la sesión sin consultar la base de datos: la tarjeta tiene que
    dibujarse incluso cuando el fallo viene de la base caída.
    """
    try:
        return (request.session.get("logueado") or {}).get("rol") == "Admin"
    except Exception:
        return False


def detalle_para_admin(request, excepcion, codigo_http):
    """Datos técnicos que solo se le muestran a un administrador."""
    if isinstance(excepcion, Exception):
        tipo = excepcion.__class__.__name__
    else:
        tipo = type(excepcion).__name__
    return {
        "codigo_http": codigo_http,
        "tipo": tipo,
        "ruta": (request.path_info if request is not None else "/")[:300],
        "metodo": request.method if request is not None else "",
    }


def pagina_amigable(request, codigo, codigo_reporte="", detalle_admin=None):
    """Responde con la tarjeta de error. Nunca lanza: si falla, responde en texto.

    El detalle técnico solo viaja al contexto cuando quien mira es Admin.
    """
    contexto = {
        "codigo": codigo,
        "codigo_reporte": codigo_reporte,
        "titulo": _TITULOS.get(codigo, "Estamos teniendo problemas"),
        "detalle_admin": detalle_admin if es_admin(request) else None,
    }
    try:
        respuesta = render(request, PLANTILLA_ERROR, contexto, status=codigo, using="errores")
    except Exception:
        logger.error("No se pudo renderizar %s (%s)", PLANTILLA_ERROR, codigo, exc_info=True)
        cuerpo = f"TecnoCorte esta teniendo problemas. Codigo HTTP {codigo}."
        if codigo == 404:
            respuesta = HttpResponseNotFound(cuerpo, content_type="text/plain; charset=utf-8")
        elif codigo == 403:
            respuesta = HttpResponseForbidden(cuerpo, content_type="text/plain; charset=utf-8")
        else:
            respuesta = HttpResponseServerError(cuerpo, content_type="text/plain; charset=utf-8")
    setattr(respuesta, MARCA_AMIGABLE, True)
    return respuesta


def tarjeta_de_fallo(request, excepcion, codigo_http):
    """Registra el fallo y devuelve la tarjeta. La usan handlers y middleware."""
    codigo = registrar_error(request, excepcion, codigo_http)
    return pagina_amigable(
        request, codigo_http, codigo, detalle_para_admin(request, excepcion, codigo_http)
    )


def pagina_no_encontrada(request, exception=None):
    """handler404: enlace inexistente o ruta borrada.

    Django lo invoca como callback(request, exception=...), por eso el
    parámetro se llama "exception" y no "excepcion".
    """
    if request.path_info in RUTAS_404_RUIDO:
        return pagina_amigable(request, 404)
    return tarjeta_de_fallo(request, exception or Http404("Página no encontrada"), 404)


def pagina_prohibida(request, exception=None):
    """handler403: sesión sin permisos para la sección."""
    return tarjeta_de_fallo(request, exception or PermissionDenied("Acceso denegado"), 403)


def error_servidor(request):
    """handler500: fallo inesperado. Recupera la traza de la señal."""
    traza = ultima_excepcion()
    excepcion = traza[1] if traza and traza[1] is not None else Exception("Error 500 sin traza registrada")
    return tarjeta_de_fallo(request, excepcion, 500)
