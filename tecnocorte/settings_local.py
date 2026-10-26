from .settings import *

# El servidor local puede recibir peticiones desde un emulador o un celular en
# la red LAN. Esta excepción solo aplica a desarrollo; producción conserva la
# lista estricta definida en `settings.py`.
ALLOWED_HOSTS = ['*']
