# Punto de entrada WSGI: permite servir el proyecto con servidores web en producción
import os
from django.core.wsgi import get_wsgi_application
# Indica qué archivo de configuración debe usar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tecnocorte.settings')
# Objeto "application" que el servidor web usa para ejecutar el proyecto
application = get_wsgi_application()
