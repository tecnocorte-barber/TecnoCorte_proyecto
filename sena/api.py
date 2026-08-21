from rest_framework import viewsets, filters
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import BasePermission
from .models import Usuario, Peluqueria, Producto, Reserva
from .serializers import UsuarioSerializer, PeluqueriaSerializer, ProductoSerializer, ReservaSerializer


def app_role(request):
    return request.session.get("logueado", {}).get("rol")


class ApiPermission(BasePermission):
    """Uses the existing application session and keeps writes for admins."""
    def has_permission(self, request, view):
        role = app_role(request)
        authenticated = bool(role) or bool(getattr(request.user, "is_authenticated", False))
        if not authenticated:
            return False
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            return role == "Admin" or bool(getattr(request.user, "is_staff", False))
        return True


class UsuarioViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre", "apellido", "email", "rol"]
    ordering_fields = ["nombre", "apellido", "fecha_creacion"]

    def get_queryset(self):
        return self.queryset if app_role(self.request) == "Admin" or self.request.user.is_staff else self.queryset.none()


class PeluqueriaViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Peluqueria.objects.all()
    serializer_class = PeluqueriaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre", "ubicacion"]
    ordering_fields = ["nombre"]


class ProductoViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre", "categoria"]
    ordering_fields = ["nombre", "precio", "fecha_creacion"]


class ReservaViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [ApiPermission]
    queryset = Reserva.objects.select_related("cliente", "peluquero", "peluqueria").all()
    serializer_class = ReservaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["cliente__nombre", "peluquero__nombre", "peluqueria__nombre", "estado"]
    ordering_fields = ["fecha", "hora", "estado"]

    def get_queryset(self):
        role = app_role(self.request)
        if role == "Admin" or self.request.user.is_staff:
            return self.queryset
        if role == "Cliente":
            return self.queryset.filter(cliente_id=self.request.session["logueado"]["id"])
        if role == "Barbero":
            return self.queryset.filter(peluquero_id=self.request.session["logueado"]["id"])
        return self.queryset.none()
