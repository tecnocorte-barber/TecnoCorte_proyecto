# Archivo de rutas URL principales del proyecto TecnoCorte
# Conecta la app "sena", el panel de administración y la documentación de la API
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

# Lista de rutas del proyecto: web principal, login de API, admin y documentación
urlpatterns = [
    path('', include('sena.urls')),
    path('api/auth/', include('rest_framework.urls')),
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
