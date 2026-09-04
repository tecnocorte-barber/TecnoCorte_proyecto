# Procesadores de contexto compartidos para las plantillas.

from .models import Notificacion, MensajeContacto, Usuario


def carrito_visible(request):
    """Evita mostrar el carrito de un usuario a otra sesión o visitante."""
    sesion = request.session
    usuario_id = (sesion.get("logueado") or {}).get("id")
    propietario_id = sesion.get("carrito_usuario_id")
    if propietario_id and propietario_id != usuario_id:
        return False
    if usuario_id and propietario_id is None and sesion.get("carrito"):
        sesion["carrito_usuario_id"] = usuario_id
    return not propietario_id or propietario_id == usuario_id


def guardar_carrito_activo(request):
    """Guarda el carrito actual bajo la cuenta que lo está utilizando."""
    sesion = request.session
    propietario_id = sesion.get("carrito_usuario_id")
    clave = str(propietario_id) if propietario_id else "anonimo"
    carritos = sesion.get("carritos_usuario", {})
    carritos[clave] = sesion.get("carrito", {})
    sesion["carritos_usuario"] = carritos


def cargar_carrito_usuario(request, usuario_id):
    """Cambia el carrito activo sin mezclarlo con el de otra cuenta."""
    guardar_carrito_activo(request)
    sesion = request.session
    carritos = sesion.get("carritos_usuario", {})
    clave = str(usuario_id)
    if clave not in carritos and carritos.get("anonimo"):
        carritos[clave] = carritos.pop("anonimo")
    sesion["carritos_usuario"] = carritos
    sesion["carrito"] = carritos.get(clave, {})
    sesion["carrito_usuario_id"] = usuario_id

# Devuelve la cantidad total de unidades del carrito guardado en la sesión
def carrito_contexto(request):
    """Expone el total de unidades del carrito en cualquier plantilla."""
    cantidad = 0
    carrito = request.session.get("carrito", {}) if carrito_visible(request) else {}
    # Suma las unidades de cada producto, ignorando valores inválidos o negativos
    for valor in carrito.values():
        try:
            cantidad += max(int(valor), 0)
        except (TypeError, ValueError):
            continue
    return {"cantidad": cantidad}


def notificaciones_contexto(request):
    """Expone contadores para que cada rol vea sus avisos pendientes."""
    sesion = request.session.get("logueado") or {}
    usuario_id = sesion.get("id")
    if not usuario_id:
        return {"notificaciones_no_leidas": 0, "mensajes_no_leidos": 0, "usuario_actual": None}
    return {
        "notificaciones_no_leidas": Notificacion.objects.filter(usuario_id=usuario_id, leida=False).count(),
        "mensajes_no_leidos": MensajeContacto.objects.filter(leido=False).count() if sesion.get("rol") == "Admin" else 0,
        "usuario_actual": Usuario.objects.filter(id=usuario_id).first(),
    }


def formulario_contexto(request):
    """Serializa los datos enviados para repoblar formularios sin incluir contraseñas."""
    if request.method != "POST":
        return {"form_post": ""}
    datos = request.POST.copy()
    for campo in ("password", "password_confirm", "password_confirmation"):
        datos.pop(campo, None)
    return {"form_post": datos.urlencode()}
