# Archivo de rutas URL principales del proyecto TecnoCorte
# Conecta la app "sena", el panel de administración y la documentación de la API
import os

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from sena import views as sena_views

# Lista de rutas del proyecto: web principal, login de API, admin y documentación
urlpatterns = [
    path('', include('sena.urls')),
    # Compatibilidad con plantillas antiguas que todavía invierten "perfil"
    # sin el namespace de la aplicación. El nombre canónico es
    # ``sena:usuario_perfil``.
    path('usuario/perfil/', sena_views.usuario_perfil, name='perfil'),
    path('api/auth/', include('rest_framework.urls')),
    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url='/static/sena/images/Logo.webp', permanent=False)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# La documentación interactiva no se publica por defecto en producción.
if settings.DEBUG or os.environ.get('API_DOCS_PUBLIC', '').lower() == 'true':
    urlpatterns += [
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ]

# Páginas de error amigables: nunca muestran la traza a la persona que navega
# y registran el fallo para que el Admin lo reciba como notificación y correo.
handler404 = 'sena.errores.pagina_no_encontrada'
handler403 = 'sena.errores.pagina_prohibida'
handler500 = 'sena.errores.error_servidor'
