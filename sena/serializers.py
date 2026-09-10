# Serializadores DRF: convierten los modelos a JSON y validan los datos de entrada
from rest_framework import serializers  # Herramientas de serialización
from django.contrib.auth.hashers import make_password  # Para cifrar contraseñas al crear/actualizar
from .models import Usuario, Peluqueria, Producto, Reserva  # Modelos a serializar


# Serializador de Usuario: expone datos básicos, oculta contraseña en lectura
class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "nombre", "apellido", "email", "password", "telefono", "rol", "fecha_creacion"]
        extra_kwargs = {
            "password": {"write_only": True},  # La contraseña solo se envía, nunca se lee
            "fecha_creacion": {"read_only": True},  # Fecha se genera automáticamente
        }

    # Al crear: cifra la contraseña antes de guardar
    def create(self, validated_data):
        validated_data["password"] = make_password(validated_data["password"])  # Hash de la contraseña
        return Usuario.objects.create(**validated_data)

    # Al actualizar: solo cifra si se envió una nueva contraseña
    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)  # Extrae la contraseña si existe
        if password:
            instance.password = make_password(password)  # Cifra la nueva contraseña
        return super().update(instance, validated_data)  # Actualiza el resto de campos


# Serializador de Peluquería: expone todos los campos
class PeluqueriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Peluqueria
        fields = "__all__"  # Todos los campos del modelo


# Serializador de Producto: expone todos los campos
class ProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = "__all__"  # Todos los campos del modelo


# Serializador de Reserva: con validaciones de servicio, cliente y barbero
class ReservaSerializer(serializers.ModelSerializer):
    # Solo permite seleccionar clientes (rol Cliente) y barberos activos
    cliente = serializers.PrimaryKeyRelatedField(queryset=Usuario.objects.filter(rol="Cliente"))
    peluquero = serializers.PrimaryKeyRelatedField(queryset=Usuario.objects.filter(rol="Barbero", activo=True))
    # Campos calculados para mostrar nombres en la respuesta
    cliente_nombre = serializers.SerializerMethodField()  # Nombre completo del cliente
    peluquero_nombre = serializers.SerializerMethodField()  # Nombre completo del barbero
    peluqueria_nombre = serializers.SerializerMethodField()  # Nombre de la peluquería

    class Meta:
        model = Reserva
        fields = [
            "id", "cliente", "peluquero", "peluqueria",
            "cliente_nombre", "peluquero_nombre", "peluqueria_nombre",
            "fecha", "hora", "estado",
            "servicio",
        ]
        extra_kwargs = {
            "peluqueria": {"write_only": True},  # La peluquería solo se envía, no se lee
        }

    # Valida que el servicio esté en la lista de servicios disponibles
    def validate_servicio(self, value):
        from .views import SERVICIOS  # Importa la lista de servicios
        if value not in {item["nombre"] for item in SERVICIOS}:
            raise serializers.ValidationError("El servicio seleccionado no es válido.")
        return value

    # Valida que el usuario tenga rol Cliente
    def validate_cliente(self, value):
        if value.rol != "Cliente":
            raise serializers.ValidationError("El cliente debe tener rol Cliente.")
        return value

    # Valida que el barbero esté activo
    def validate_peluquero(self, value):
        if value.rol != "Barbero" or not value.activo:
            raise serializers.ValidationError("El barbero no está disponible para nuevas citas.")
        return value

    # Devuelve nombre completo del cliente para la respuesta JSON
    def get_cliente_nombre(self, obj) -> str:
        return f"{obj.cliente.nombre} {obj.cliente.apellido}"

    # Devuelve nombre completo del barbero para la respuesta JSON
    def get_peluquero_nombre(self, obj) -> str:
        return f"{obj.peluquero.nombre} {obj.peluquero.apellido}"

    # Devuelve el nombre de la peluquería para la respuesta JSON
    def get_peluqueria_nombre(self, obj) -> str:
        return obj.peluqueria.nombre
