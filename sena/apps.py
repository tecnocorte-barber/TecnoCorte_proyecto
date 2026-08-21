# Configuración de la aplicación "sena" (núcleo de la barbería TecnoCorte)
from django.apps import AppConfig

# Clase que registra la app y define su tipo de clave primaria por defecto
class SenaConfig(AppConfig):
    default_auto_field = 'django.db.models.AutoField'
    name = 'sena'
