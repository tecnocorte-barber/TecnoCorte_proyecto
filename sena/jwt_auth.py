"""JWT compatible con el modelo de usuario propio de TecnoCorte."""
from datetime import datetime, timedelta, timezone
import hashlib
import uuid
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from .models import Usuario, JWTRefreshToken

try:
    from drf_spectacular.extensions import OpenApiAuthenticationExtension
except ImportError:  # Permite importar el módulo en instalaciones mínimas.
    OpenApiAuthenticationExtension = None

class JWTUser:
    def __init__(self, usuario):
        self.usuario = usuario
        self.id, self.rol, self.email = usuario.id, usuario.rol, usuario.email
        self.pk = usuario.pk
        self.is_staff = usuario.rol == "Admin"
        self.is_authenticated = True

def crear_token(usuario, tipo="access"):
    ahora = datetime.now(timezone.utc)
    duracion = timedelta(minutes=settings.JWT_ACCESS_MINUTES) if tipo == "access" else timedelta(days=settings.JWT_REFRESH_DAYS)
    datos = {"sub": str(usuario.id), "role": usuario.rol, "version": usuario.sesion_version,
             "type": tipo, "iat": ahora, "exp": ahora + duracion}
    if tipo == "refresh":
        datos["jti"] = uuid.uuid4().hex
        JWTRefreshToken.objects.create(
            usuario=usuario,
            jti_hash=hashlib.sha256(datos["jti"].encode()).hexdigest(),
            expira=datos["exp"],
        )
    return jwt.encode(datos, settings.SECRET_KEY, algorithm="HS256")

def decodificar_token(token):
    try:
        datos = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AuthenticationFailed("Token inválido o expirado.") from exc
    usuario = Usuario.objects.filter(id=datos.get("sub"), activo=True).first()
    if not usuario or usuario.sesion_version != datos.get("version"):
        raise AuthenticationFailed("La sesión ya no es válida.")
    if datos.get("type") == "refresh":
        jti = datos.get("jti", "")
        vigente = JWTRefreshToken.objects.filter(
            usuario=usuario,
            jti_hash=hashlib.sha256(jti.encode()).hexdigest(),
            revocado=False,
            expira__gt=datetime.now(timezone.utc),
        ).first()
        if vigente is None:
            raise AuthenticationFailed("Refresh token revocado o ya utilizado.")
    return datos, usuario


def revocar_refresh(datos):
    """Revoca un refresh token para impedir su reutilización."""
    if datos.get("type") != "refresh" or not datos.get("jti"):
        return
    JWTRefreshToken.objects.filter(
        jti_hash=hashlib.sha256(datos["jti"].encode()).hexdigest(), revocado=False
    ).update(revocado=True, revocado_en=datetime.now(timezone.utc))

class JWTAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        partes = get_authorization_header(request).split()
        if not partes:
            return None
        if len(partes) != 2 or partes[0].lower() != b"bearer":
            raise AuthenticationFailed("Usa Authorization: Bearer <token>.")
        datos, usuario = decodificar_token(partes[1].decode())
        if datos.get("type") != "access":
            raise AuthenticationFailed("Se requiere un access token.")
        return JWTUser(usuario), datos


if OpenApiAuthenticationExtension:
    class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
        target_class = "sena.jwt_auth.JWTAuthentication"
        name = "JWTBearer"

        def get_security_definition(self, auto_schema):
            return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
