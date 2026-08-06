from django.contrib import admin
from django.urls import path, include

from django.urls import path
from rest_framework import routers
router = routers.DefaultRouter()
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
 

urlpatterns = [
    path('', include('sena.urls')),
    path('api/auth/', include('rest_framework.urls')),
    path('admin/', admin.site.urls),
    # Documentación
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/', include(router.urls)),

    #login apis
    path('api/auth/', include('rest_framework.urls')),

]
