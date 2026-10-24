# Funciones de ayuda del proyecto: validación de contraseñas y control de acceso por roles
from django.shortcuts import redirect
from django.urls import reverse
from functools import wraps
import re

from PIL import Image, UnidentifiedImageError
from .services.auditoria import registrar_accion

MAX_IMAGEN_BYTES = 5 * 1024 * 1024
FORMATOS_IMAGEN_PERMITIDOS = {"JPEG", "PNG", "WEBP"}

TRANSICIONES_RESERVA = {
    "Pendiente": {"Pendiente", "Confirmada", "Cancelada"},
    "Confirmada": {"Confirmada", "Completada", "Cancelada"},
    "Completada": {"Completada"},
    # El Admin puede devolver una cita cancelada a Pendiente para reagendarla.
    "Cancelada": {"Cancelada", "Pendiente"},
}

TRANSICIONES_PEDIDO = {
    "Pendiente": {"Pendiente", "Listo", "Entregado", "Cancelado"},
    "Listo": {"Listo", "Entregado", "Cancelado"},
    "Entregado": {"Entregado"},
    "Completado": {"Completado"},
    "Cancelado": {"Cancelado"},
}


def transicion_valida(mapa, anterior, nuevo):
    """Indica si un objeto puede pasar de un estado a otro."""
    return nuevo in mapa.get(anterior, set())

# Reglas de contraseña: mínimo 8 caracteres, una mayúscula, un número y un símbolo
def validar_password(password):
    """Devuelve un mensaje de error si la contraseña no cumple las reglas, o "" si es válida."""
    if len(password or "") < 8:
        return "La contraseña debe tener mínimo 8 caracteres."
    if not re.search(r"[A-Z]", password):
        return "La contraseña debe tener al menos una letra mayúscula."
    if not re.search(r"[0-9]", password):
        return "La contraseña debe tener al menos un número."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "La contraseña debe tener al menos un símbolo (ej: !@#$%)."
    return ""


def validar_telefono(telefono, obligatorio=False):
    """Valida teléfonos nacionales o internacionales sin aceptar contenido arbitrario."""
    telefono = (telefono or "").strip()
    if not telefono:
        return "El teléfono es obligatorio." if obligatorio else ""
    if not re.fullmatch(r"\+?[0-9 ()-]{7,20}", telefono):
        return "El teléfono solo puede contener números, espacios, paréntesis y guiones."
    if len(re.sub(r"\D", "", telefono)) < 7:
        return "El teléfono debe tener al menos 7 dígitos."
    return ""


def validar_imagen(archivo):
    """Valida tamaño, contenido real y formato antes de guardar una imagen subida."""
    if not archivo:
        return ""
    if getattr(archivo, "size", 0) > MAX_IMAGEN_BYTES:
        return "La imagen no puede superar los 5 MB."
    try:
        archivo.seek(0)
        with Image.open(archivo) as imagen:
            imagen.verify()
            if imagen.format not in FORMATOS_IMAGEN_PERMITIDOS:
                return "Solo se permiten imágenes JPG, PNG o WEBP."
        archivo.seek(0)
    except (UnidentifiedImageError, OSError, ValueError):
        try:
            archivo.seek(0)
        except (OSError, ValueError):
            pass
        return "El archivo seleccionado no es una imagen válida."
    return ""


# Decorador que protege vistas: exige sesión iniciada y, opcionalmente, un rol permitido
def autorizacion(roles=[]):
    def decorador(vista):
        @wraps(vista)
        def envoltorio(request, *args, **kwargs):
            # Si no hay sesión activa, redirige al login guardando la página destino
            if not request.session.get("logueado"):
                login_url = reverse("sena:login")
                return redirect(f"{login_url}?next={request.path_info}")
            
            # Verifica que el usuario de la sesión exista y esté activo
            from sena.models import Usuario
            usuario = Usuario.objects.filter(id=request.session["logueado"]["id"], activo=True).first()
            if usuario is None:
                del request.session["logueado"]
                return redirect("sena:login")

            # Una nueva versión invalida las sesiones que existían antes de un
            # cambio de contraseña o de una acción de cierre global.
            version_sesion = request.session["logueado"].get("sesion_version")
            if version_sesion is not None and version_sesion != usuario.sesion_version:
                request.session.flush()
                return redirect("sena:login")
            
            # Si se indicaron roles, comprueba que el rol del usuario esté permitido
            if roles:
                rol = request.session["logueado"]["rol"]
                if rol not in roles:
                    return redirect("sena:login")
            
            return vista(request, *args, **kwargs)
        # Deja constancia de los roles permitidos para poder auditar las rutas
        # desde los tests (ver test_toda_vista_de_panel_tiene_autorizacion).
        envoltorio.roles_permitidas = list(roles)
        return envoltorio
    return decorador
