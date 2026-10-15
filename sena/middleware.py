# Middleware del proyecto TecnoCorte.
# Se encarga de aplicar el modo mantenimiento configurado por el Admin.
from django.conf import settings
from django.shortcuts import render

from .models import Configuracion


class MantenimientoMiddleware:
    """Si el modo mantenimiento está activo, solo el Admin puede navegar el sitio."""

    # Rutas que siempre deben quedar accesibles (login, logout, admin de Django, archivos).
    PREFIJOS_PERMITIDOS = (
        "/login/",
        "/logout/",
        "/admin/",
        str(settings.STATIC_URL),
        str(settings.MEDIA_URL),
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            config = Configuracion.cargar()
        except Exception:
            # Si la base de datos no responde, no se bloquea el sitio por esta causa.
            return self.get_response(request)

        if config.modo_mantenimiento:
            sesion = request.session.get("logueado") or {}
            es_admin = sesion.get("rol") == "Admin"
            ruta_permitida = request.path.startswith(self.PREFIJOS_PERMITIDOS)
            if not es_admin and not ruta_permitida:
                return render(request, "publicos/mantenimiento.html", {"config": config}, status=503)

        return self.get_response(request)
