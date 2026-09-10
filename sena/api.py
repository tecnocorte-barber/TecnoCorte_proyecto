# API REST: ViewSets que exponen los modelos como endpoints JSON
# Usa autenticación por sesión (web) o token (externo), con permisos por rol
from rest_framework import viewsets, filters  # ViewSets base y filtros de búsqueda/orden
from rest_framework.authentication import SessionAuthentication, TokenAuthentication  # Dos métodos de autenticación
from rest_framework.permissions import IsAuthenticated  # Permisos base de DRF
from rest_framework.permissions import BasePermission  # Para crear permiso personalizado
from .models import Usuario, Peluqueria, Producto, Reserva  # Modelos que expone la API
from .serializers import UsuarioSerializer, PeluqueriaSerializer, ProductoSerializer, ReservaSerializer  # Serializadores


def app_role(request):
    """Obtiene el rol del usuario desde la sesión de la aplicación web."""
    return request.session.get("logueado", {}).get("rol")


# Permiso personalizado: verifica sesión activa y restringe escritura a admins
class ApiPermission(BasePermission):
    """Permite lectura a cualquier usuario autenticado, escritura solo a Admin."""
    def has_permission(self, request, view):
        role = app_role(request)  # Rol de la sesión web
        authenticated = bool(role) or bool(getattr(request.user, "is_authenticated", False))  # Sesión o token
        if not authenticated:
            return False  # Sin autenticación, no hay acceso
        # Escritura (POST/PUT/PATCH/DELETE) solo para Admin o staff
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            return role == "Admin" or bool(getattr(request.user, "is_staff", False))
        return True  # Lectura permitida para cualquier autenticado


# CRUD de usuarios: solo Admin puede listar todos los usuarios
class UsuarioViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]  # Acepta token o sesión
    permission_classes = [ApiPermission]  # Usa nuestro permiso personalizado
    queryset = Usuario.objects.all()  # Query base: todos los usuarios
    serializer_class = UsuarioSerializer  # Serializador con campos definidos
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]  # Búsqueda y orden
    search_fields = ["nombre", "apellido", "email", "rol"]  # Campos buscables
    ordering_fields = ["nombre", "apellido", "fecha_creacion"]  # Campos ordenables

    # Solo Admin ve todos los usuarios; otros no ven nada
    def get_queryset(self):
        return self.queryset if app_role(self.request) == "Admin" or self.request.user.is_staff else self.queryset.none()


# CRUD de peluquerías (sedes): visible para cualquier autenticado
class PeluqueriaViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Peluqueria.objects.all()  # Todas las sedes
    serializer_class = PeluqueriaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre", "ubicacion"]  # Buscar por nombre o dirección
    ordering_fields = ["nombre"]


# CRUD de productos de la tienda
class ProductoViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Producto.objects.all()  # Todos los productos
    serializer_class = ProductoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre", "categoria"]  # Buscar por nombre o categoría
    ordering_fields = ["nombre", "precio", "fecha_creacion"]  # Ordenar por nombre, precio o fecha


# CRUD de reservas (citas): cada rol solo ve las que le corresponden
class ReservaViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Reserva.objects.select_related("cliente", "peluquero", "peluqueria").all()  # Consulta optimizada con relaciones
    serializer_class = ReservaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["cliente__nombre", "peluquero__nombre", "peluqueria__nombre", "estado"]  # Buscar por nombre de cliente/barbero/sede o estado
    ordering_fields = ["fecha", "hora", "estado"]

    # Filtra reservas según el rol: Admin ve todo, cliente/barbero solo las suyas
    def get_queryset(self):
        role = app_role(self.request)
        if role == "Admin" or self.request.user.is_staff:
            return self.queryset  # Admin ve todo
        if role == "Cliente":
            return self.queryset.filter(cliente_id=self.request.session["logueado"]["id"])  # Solo sus citas
        if role == "Barbero":
            return self.queryset.filter(peluquero_id=self.request.session["logueado"]["id"])  # Solo sus citas
        return self.queryset.none()  # Sin rol válido, no ve nada
