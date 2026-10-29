# Middleware del proyecto TecnoCorte.
# Aplica el modo mantenimiento configurado por el Admin y garantiza que
# cualquier fallo termine en la tarjeta de error amigable.
import os
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render

from .errores import es_amigable, tarjeta_de_fallo, ultima_excepcion, RUTAS_404_RUIDO
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


class ErroresAmigablesMiddleware:
    """Convierte cualquier fallo en la tarjeta de error amigable.

    Django solo usa handler404/handler403/handler500 cuando DEBUG está apagado:
    en desarrollo responde con su página amarilla de depuración. Este
    middleware intercepta esos casos para que quien navega vea siempre la misma
    tarjeta, en cualquier entorno. El detalle técnico no se pierde: queda en
    RegistroError, en el log y en el aviso al Admin, y se dibuja en la propia
    tarjeta cuando quien la ve tiene sesión de administrador.
    """

    # Rutas que nunca se convierten en tarjeta: se espera otro formato (JSON) y
    # sustituirlo rompería a quien las consume.
    PREFIJOS_SIN_TARJETA = (
        "/api/",
        str(settings.STATIC_URL),
        str(settings.MEDIA_URL),
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # process_response no lo invoca Django en middlewares nuevos: la
        # revisión de la respuesta va aquí, igual que en MantenimientoMiddleware.
        return self._revisar(request, self.get_response(request))

    def _sin_tarjeta(self, request):
        return request.path.startswith(self.PREFIJOS_SIN_TARJETA)

    def _ruido_404(self, request):
        """Sondas externas conocidas: se responden 404 sin llenar la auditoría."""
        return request.path_info in RUTAS_404_RUIDO

    def process_exception(self, request, exception):
        """Excepción de la vista: 404, 403 o fallo inesperado."""
        if not isinstance(exception, Exception) or self._sin_tarjeta(request):
            return None
        if isinstance(exception, Http404) and self._ruido_404(request):
            return None
        if isinstance(exception, Http404):
            codigo_http = 404
        elif isinstance(exception, PermissionDenied):
            codigo_http = 403
        else:
            codigo_http = 500
        return tarjeta_de_fallo(request, exception, codigo_http)

    def _revisar(self, request, response):
        """Cubre lo que no pasa por una excepción: el 404 del resolutor de URLs.

        Con DEBUG apagado ese 404 ya viene convertido por handler404 (marcado
        como tarjeta), así que aquí solo se sustituye la página de depuración.
        """
        if (
            response.status_code in (404, 500)
            and not es_amigable(response)
            and not self._sin_tarjeta(request)
            and not self._ruido_404(request)
            and "text/html" in response.get("Content-Type", "text/html")
        ):
            if response.status_code == 404:
                excepcion = Http404("Página no encontrada")
            else:
                traza = ultima_excepcion()
                excepcion = traza[1] if traza and traza[1] is not None else Exception(
                    "Error 500 sin traza registrada"
                )
            return tarjeta_de_fallo(request, excepcion, response.status_code)
        return response


class CorsMiddleware:
    """Permite que la app Flutter (web) consuma la API durante el desarrollo."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.META.get("HTTP_ORIGIN", "")
        allowed = False
        if getattr(settings, "DEBUG", False):
            allowed = bool(origin)
        else:
            allowed_origins = [
                item.strip() for item in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if item.strip()
            ]
            allowed = origin in allowed_origins
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if allowed and origin:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response["Access-Control-Max-Age"] = "86400"
            response["Vary"] = "Origin"
        return response
