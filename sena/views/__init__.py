"""Fachada pública de vistas conservando la implementación remota integrada."""
from .remote import *  # noqa: F401,F403
from .remote import (
    _horarios_para_template, _invalidar_cache_disponibilidad, _borrar_archivo,
    _reservas_para_template, _json_seguro, _id_entero, _pestanas_config,
    _datos_notificacion, _datos_descargables, _respuesta_reporte_excel,
    _peluqueria_del_barbero, _motivo_eliminacion,
)
# Registro, inicio de sesión y verificación deben compartir el mismo flujo:
# el registro pendiente vive en la base de datos y se recupera por token, no
# desde la sesión del navegador ni desde la caché de una instancia.
from .autenticacion import (  # noqa: E402
    login, registro, verificar_correo, reenviar_verificacion,
)
# Importar las vistas modulares de autenticación carga también módulos cuyo
# nombre coincide con una vista histórica expuesta desde este paquete.
from .remote import carrito as carrito  # noqa: E402,F401
for _nombre, _objeto in list(globals().items()):
    if callable(_objeto) and getattr(_objeto, "__module__", "") == "sena.views.remote":
        _objeto.__module__ = __name__
del _nombre, _objeto
