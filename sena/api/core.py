# API REST: ViewSets que exponen los modelos como endpoints JSON
# Usa autenticación por sesión (web) o token (externo), con permisos por rol
from rest_framework import viewsets, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from drf_spectacular.utils import extend_schema
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication, TokenAuthentication  # Dos métodos de autenticación
from rest_framework.permissions import IsAuthenticated  # Permisos base de DRF
from rest_framework.permissions import BasePermission  # Para crear permiso personalizado
from ..models import Usuario, Peluqueria, Producto, Reserva, Pedido, PedidoProducto, Notificacion  # Modelos que expone la API
from ..serializers import (UsuarioSerializer, PeluqueriaSerializer, ProductoSerializer, ReservaSerializer,
                           PedidoSerializer, PedidoProductoSerializer, NotificacionSerializer,
                           TokenRequestSerializer, RefreshTokenRequestSerializer, TokenResponseSerializer,
                           MessageResponseSerializer, RegistroRequestSerializer)
from ..utilidades import registrar_accion
from ..jwt_auth import JWTAuthentication, crear_token, decodificar_token, revocar_refresh


def app_role(request):
    """Obtiene el rol del usuario desde la sesión de la aplicación web."""
    return getattr(getattr(request, "user", None), "rol", None) or request.session.get("logueado", {}).get("rol")


def app_usuario(request):
    """Usuario propio de la aplicación cuando la API usa sesión web."""
    jwt_usuario = getattr(getattr(request, "user", None), "usuario", None)
    if jwt_usuario:
        return jwt_usuario
    sesion = request.session.get("logueado", {})
    if not sesion.get("id"):
        return None
    usuario = Usuario.objects.filter(id=sesion["id"], activo=True).first()
    if usuario and sesion.get("sesion_version") not in (None, usuario.sesion_version):
        return None
    return usuario


# Permiso personalizado: verifica sesión activa y restringe escritura a admins
class ApiPermission(BasePermission):
    """Permite lectura a cualquier usuario autenticado, escritura solo a Admin."""
    def has_permission(self, request, view):
        role = app_role(request)  # Rol de la sesión web
        authenticated = bool(app_usuario(request)) or bool(getattr(request.user, "is_authenticated", False))  # Sesión o token
        if not authenticated:
            return False  # Sin autenticación, no hay acceso
        # Escritura (POST/PUT/PATCH/DELETE) solo para Admin/SuperAdmin o staff
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            # Los clientes pueden crear citas propias; el resto de escrituras
            # conserva la restricción administrativa.
            if (request.method == "POST" and isinstance(view, ReservaViewSet)
                    and role == "Cliente"):
                return True
            return role in ("Admin", "SuperAdmin") or bool(getattr(request.user, "is_staff", False))
        return True  # Lectura permitida para cualquier autenticado


class AuditedModelViewSet(viewsets.ModelViewSet):
    """ViewSet común: registra escrituras de API en la auditoría."""
    def perform_create(self, serializer):
        objeto = serializer.save()
        registrar_accion(self.request, "api_crear", objeto.__class__.__name__, objeto.pk)

    def perform_update(self, serializer):
        objeto = serializer.save()
        registrar_accion(self.request, "api_actualizar", objeto.__class__.__name__, objeto.pk)

    def perform_destroy(self, instance):
        entidad, entidad_id = instance.__class__.__name__, instance.pk
        instance.delete()
        registrar_accion(self.request, "api_eliminar", entidad, entidad_id)


# CRUD de usuarios: solo Admin puede listar todos los usuarios
class UsuarioViewSet(AuditedModelViewSet):
    authentication_classes = [JWTAuthentication, TokenAuthentication, SessionAuthentication]  # Acepta token o sesión
    permission_classes = [ApiPermission]  # Usa nuestro permiso personalizado
    queryset = Usuario.objects.all()  # Query base: todos los usuarios
    serializer_class = UsuarioSerializer  # Serializador con campos definidos
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]  # Búsqueda y orden
    search_fields = ["nombre", "apellido", "email", "rol"]  # Campos buscables
    ordering_fields = ["nombre", "apellido", "fecha_creacion"]  # Campos ordenables

    def _puede_gestionar_roles(self):
        usuario = app_usuario(self.request)
        return bool(usuario and usuario.rol in ("Admin", "SuperAdmin"))

    def _roles_permitidos(self):
        usuario = app_usuario(self.request)
        if usuario and usuario.rol == "SuperAdmin":
            return {"Cliente", "Barbero", "Admin"}
        return {"Cliente", "Barbero"}

    def perform_create(self, serializer):
        rol = serializer.validated_data.get("rol", "Cliente")
        if rol not in self._roles_permitidos():
            raise PermissionDenied("No tienes permiso para asignar ese rol.")
        objeto = serializer.save(rol=rol)
        registrar_accion(self.request, "api_crear", objeto.__class__.__name__, objeto.pk)

    def perform_update(self, serializer):
        if "password" in serializer.validated_data:
            raise PermissionDenied(
                "Los administradores no pueden cambiar contraseñas de usuarios."
            )
        if "rol" in serializer.validated_data:
            nuevo_rol = serializer.validated_data["rol"]
            actor = app_usuario(self.request)
            if nuevo_rol not in self._roles_permitidos():
                raise PermissionDenied("No tienes permiso para asignar ese rol.")
            if actor and actor.rol != "SuperAdmin" and serializer.instance.rol in ("Admin", "SuperAdmin"):
                raise PermissionDenied("Un Admin no puede modificar permisos administrativos.")
        super().perform_update(serializer)

    # Solo Admin ve todos los usuarios; otros no ven nada
    def get_queryset(self):
        return self.queryset if app_role(self.request) in ("Admin", "SuperAdmin") or self.request.user.is_staff else self.queryset.none()


# CRUD de peluquerías (sedes): visible para cualquier autenticado
class PeluqueriaViewSet(AuditedModelViewSet):
    authentication_classes = [JWTAuthentication, TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Peluqueria.objects.all()  # Todas las sedes
    serializer_class = PeluqueriaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre", "ubicacion"]  # Buscar por nombre o dirección
    ordering_fields = ["nombre"]


# CRUD de productos de la tienda
class ProductoViewSet(AuditedModelViewSet):
    authentication_classes = [JWTAuthentication, TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Producto.objects.all()  # Todos los productos
    serializer_class = ProductoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre", "categoria"]  # Buscar por nombre o categoría
    ordering_fields = ["nombre", "precio", "fecha_creacion"]  # Ordenar por nombre, precio o fecha


# CRUD de reservas (citas): cada rol solo ve las que le corresponden
class ReservaViewSet(AuditedModelViewSet):
    authentication_classes = [JWTAuthentication, TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Reserva.objects.select_related("cliente", "peluquero", "peluqueria").all()  # Consulta optimizada con relaciones
    serializer_class = ReservaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["cliente__nombre", "peluquero__nombre", "peluqueria__nombre", "estado"]  # Buscar por nombre de cliente/barbero/sede o estado
    ordering_fields = ["fecha", "hora", "estado"]

    # Filtra reservas según el rol: Admin ve todo, cliente/barbero solo las suyas
    def get_queryset(self):
        role = app_role(self.request)
        if role in ("Admin", "SuperAdmin") or self.request.user.is_staff:
            return self.queryset  # Admin ve todo
        if role == "Cliente":
            return self.queryset.filter(cliente=app_usuario(self.request))  # Solo sus citas
        if role == "Barbero":
            return self.queryset.filter(peluquero=app_usuario(self.request))  # Solo sus citas
        return self.queryset.none()  # Sin rol válido, no ve nada

    def perform_create(self, serializer):
        usuario = app_usuario(self.request)
        if app_role(self.request) == "Cliente":
            objeto = serializer.save(cliente=usuario, estado="Pendiente")
        else:
            objeto = serializer.save()
        registrar_accion(self.request, "api_crear", objeto.__class__.__name__, objeto.pk)


class PedidoViewSet(AuditedModelViewSet):
    """Pedidos equivalentes al endpoint de pedidos de Node.js."""
    authentication_classes = [JWTAuthentication, TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Pedido.objects.select_related("cliente").all()
    serializer_class = PedidoSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["fecha", "estado", "total"]

    def get_queryset(self):
        if app_role(self.request) in ("Admin", "SuperAdmin") or self.request.user.is_staff:
            return self.queryset
        usuario = app_usuario(self.request)
        return self.queryset.filter(cliente=usuario) if usuario else self.queryset.none()

    def perform_create(self, serializer):
        usuario = app_usuario(self.request)
        objeto = serializer.save(cliente=usuario)
        registrar_accion(self.request, "api_crear", objeto.__class__.__name__, objeto.pk)


class PedidoProductoViewSet(AuditedModelViewSet):
    """Detalle de productos de los pedidos."""
    authentication_classes = [JWTAuthentication, TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = PedidoProducto.objects.select_related("pedido", "producto").all()
    serializer_class = PedidoProductoSerializer

    def get_queryset(self):
        if app_role(self.request) in ("Admin", "SuperAdmin") or self.request.user.is_staff:
            return self.queryset
        usuario = app_usuario(self.request)
        return self.queryset.filter(pedido__cliente=usuario) if usuario else self.queryset.none()


class NotificacionViewSet(viewsets.ReadOnlyModelViewSet):
    """Notificaciones privadas del usuario autenticado."""
    authentication_classes = [JWTAuthentication, TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    serializer_class = NotificacionSerializer
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        usuario = app_usuario(self.request)
        return Notificacion.objects.filter(usuario=usuario).select_related("reserva") if usuario else Notificacion.objects.none()


class TokenView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(request=TokenRequestSerializer, responses={200: TokenResponseSerializer, 401: MessageResponseSerializer})
    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        password = request.data.get("password", "")
        from django.contrib.auth.hashers import check_password
        usuario = Usuario.objects.filter(email__iexact=email, activo=True).first()
        if not usuario or not check_password(password, usuario.password):
            return Response({"detail": "Credenciales inválidas."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"access": crear_token(usuario), "refresh": crear_token(usuario, "refresh"),
                         "expires_in": settings.JWT_ACCESS_MINUTES * 60})


class RegistroView(APIView):
    """Registro público de clientes para la aplicación móvil."""
    authentication_classes = []
    permission_classes = []

    @extend_schema(request=RegistroRequestSerializer, responses={201: TokenResponseSerializer,
                                                                  400: MessageResponseSerializer})
    def post(self, request):
        datos = RegistroRequestSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        valores = datos.validated_data
        email = valores["email"].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            return Response({"detail": "Ya existe una cuenta con ese correo."}, status=status.HTTP_400_BAD_REQUEST)
        from ..utilidades import validar_password
        error = validar_password(valores["password"])
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
        usuario = Usuario.objects.create(
            nombre=valores["nombre"].strip(), apellido=valores["apellido"].strip(),
            email=email, telefono=valores.get("telefono", "").strip(),
            password=make_password(valores["password"]), rol="Cliente",
            email_verificado=True,
        )
        return Response({"access": crear_token(usuario), "refresh": crear_token(usuario, "refresh"),
                         "expires_in": settings.JWT_ACCESS_MINUTES * 60}, status=status.HTTP_201_CREATED)


class ServicioListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from ..services.catalogo import catalogo_servicios
        return Response(catalogo_servicios())


class BarberoListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        barberos = Usuario.objects.filter(rol="Barbero", activo=True,
                                          peluqueria__isnull=False).select_related("peluqueria")
        return Response([{"id": b.id, "nombre": f"{b.nombre} {b.apellido}",
                          "telefono": b.telefono, "peluqueria": b.peluqueria_id,
                          "peluqueria_nombre": b.peluqueria.nombre} for b in barberos])


class RefreshTokenView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(request=RefreshTokenRequestSerializer, responses={200: TokenResponseSerializer, 401: MessageResponseSerializer})
    def post(self, request):
        try:
            datos, usuario = decodificar_token(str(request.data.get("refresh", "")))
            if datos.get("type") != "refresh":
                raise ValueError
            revocar_refresh(datos)
        except (AuthenticationFailed, ValueError, TypeError, KeyError):
            return Response({"detail": "Refresh token inválido o expirado."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"access": crear_token(usuario), "refresh": crear_token(usuario, "refresh"),
                         "expires_in": settings.JWT_ACCESS_MINUTES * 60})


class LogoutTokenView(APIView):
    authentication_classes = [JWTAuthentication]

    @extend_schema(request=None, responses={200: MessageResponseSerializer})
    def post(self, request):
        usuario = app_usuario(request)
        usuario.sesion_version += 1
        usuario.save(update_fields=["sesion_version"])
        from ..models import JWTRefreshToken
        JWTRefreshToken.objects.filter(usuario=usuario, revocado=False).update(
            revocado=True, revocado_en=timezone.now()
        )
        registrar_accion(request, "cierre_sesiones_jwt", "Usuario", usuario.id)
        return Response({"detail": "Sesiones invalidadas."})
