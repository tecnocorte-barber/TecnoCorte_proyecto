# Configuración de la aplicación "sena" (núcleo de la barbería TecnoCorte)
from django.apps import AppConfig

# Clase que registra la app y define su tipo de clave primaria por defecto
class SenaConfig(AppConfig):
    default_auto_field = 'django.db.models.AutoField'
    name = 'sena'

    def ready(self):
        # Importa sena.errores al arrancar para que la señal
        # got_request_exception quede conectada antes de la primera petición.
        # Si no, el handler500 se importaría tarde y perdería la traza.
        from . import errores  # noqa: F401
