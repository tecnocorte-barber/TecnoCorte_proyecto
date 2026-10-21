"""Fachada pública de vistas conservando la implementación remota integrada."""
from .remote import *  # noqa: F401,F403
from .remote import (
    _horarios_para_template, _invalidar_cache_disponibilidad, _borrar_archivo,
    _reservas_para_template, _json_seguro, _id_entero, _pestanas_config,
    _datos_notificacion, _datos_descargables, _respuesta_reporte_excel,
    _peluqueria_del_barbero, _motivo_eliminacion,
)
for _nombre, _objeto in list(globals().items()):
    if callable(_objeto) and getattr(_objeto, "__module__", "") == "sena.views.remote":
        _objeto.__module__ = __name__
del _nombre, _objeto
