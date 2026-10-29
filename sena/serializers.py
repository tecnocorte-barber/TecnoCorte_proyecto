# Serializadores DRF: convierten los modelos a JSON y validan los datos de entrada
from rest_framework import serializers  # Herramientas de serialización
from .utilidades import TRANSICIONES_RESERVA, transicion_valida
from django.contrib.auth.hashers import make_password  # Para cifrar contraseñas al crear/actualizar
from .models import Usuario, Peluqueria, Producto, Reserva, Pedido, PedidoProducto, Notificacion  # Modelos a serializar


class TokenRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class RefreshTokenRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField(required=False)
    expires_in = serializers.IntegerField()


class RegistroRequestSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=100)
    apellido = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    telefono = serializers.CharField(max_length=20, required=False, allow_blank=True)


class MessageResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


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
        fields = ["id", "nombre", "ubicacion", "telefono", "dueno", "descripcion", "imagen"]


# Serializador de Producto: expone todos los campos
class ProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = ["id", "nombre", "descripcion", "precio", "imagen", "categoria", "stock", "disponible", "fecha_creacion"]
        read_only_fields = ["fecha_creacion"]

    def validate_precio(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio no puede ser negativo.")
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("El stock no puede ser negativo.")
        return value

    def validate(self, attrs):
        stock = attrs.get("stock", getattr(self.instance, "stock", 0))
        if attrs.get("disponible", getattr(self.instance, "disponible", True)) and stock <= 0:
            raise serializers.ValidationError({"disponible": "Un producto disponible debe tener stock."})
        return attrs


# Serializador de Reserva: con validaciones de servicio, cliente y barbero
class ReservaSerializer(serializers.ModelSerializer):
    # Solo permite seleccionar clientes (rol Cliente) y barberos activos
    cliente = serializers.PrimaryKeyRelatedField(queryset=Usuario.objects.filter(rol="Cliente", activo=True), required=False)
    peluquero = serializers.PrimaryKeyRelatedField(queryset=Usuario.objects.filter(rol="Barbero", activo=True))
    peluqueria = serializers.PrimaryKeyRelatedField(queryset=Peluqueria.objects.all(), write_only=True)
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

    # Valida que el servicio esté en el catálogo (base o aprobado a un barbero)
    def validate_servicio(self, value):
        from .views import servicio_valido  # Importa el validador del catálogo
        if not servicio_valido(value):
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

    def validate_estado(self, value):
        if value not in {estado[0] for estado in Reserva.ESTADOS}:
            raise serializers.ValidationError("El estado de la reserva no es válido.")
        return value

    def validate(self, attrs):
        """Aplica las reglas de sede, horario y cruces también en la API."""
        if self.instance and "estado" in attrs and not transicion_valida(
            TRANSICIONES_RESERVA, self.instance.estado, attrs["estado"]
        ):
            raise serializers.ValidationError(
                {"estado": f"No se puede pasar una cita de {self.instance.estado} a {attrs['estado']}."}
            )
        peluquero = attrs.get("peluquero", getattr(self.instance, "peluquero", None))
        peluqueria = attrs.get("peluqueria", getattr(self.instance, "peluqueria", None))
        fecha = attrs.get("fecha", getattr(self.instance, "fecha", None))
        hora = attrs.get("hora", getattr(self.instance, "hora", None))
        servicio = attrs.get("servicio", getattr(self.instance, "servicio", ""))
        if peluquero and peluqueria and peluquero.peluqueria_id != peluqueria.id:
            raise serializers.ValidationError("El barbero no pertenece a la peluquería seleccionada.")
        if fecha and hora and peluqueria and servicio:
            from .views import barbero_esta_disponible, cita_disponible

            fecha_texto = fecha.isoformat()
            hora_texto = hora.strftime("%H:%M")
            disponible, mensaje = cita_disponible(fecha_texto, hora_texto, peluqueria.id, servicio)
            if not disponible:
                raise serializers.ValidationError(mensaje)
            disponible, mensaje = barbero_esta_disponible(
                peluquero.id, fecha_texto, hora_texto, servicio, self.instance
            )
            if not disponible:
                raise serializers.ValidationError(mensaje)
        return attrs

    # Devuelve nombre completo del cliente para la respuesta JSON
    def get_cliente_nombre(self, obj) -> str:
        return f"{obj.cliente.nombre} {obj.cliente.apellido}"

    # Devuelve nombre completo del barbero para la respuesta JSON
    def get_peluquero_nombre(self, obj) -> str:
        return f"{obj.peluquero.nombre} {obj.peluquero.apellido}"

    # Devuelve el nombre de la peluquería para la respuesta JSON
    def get_peluqueria_nombre(self, obj) -> str:
        return obj.peluqueria.nombre


class PedidoSerializer(serializers.ModelSerializer):
    """Serializa pedidos sin permitir cambiar el cliente desde la API."""
    class Meta:
        model = Pedido
        fields = ["id", "cliente", "fecha", "total", "estado", "pago_confirmado", "fecha_pago", "fecha_entrega"]
        read_only_fields = ["cliente", "fecha", "total", "fecha_pago", "fecha_entrega"]


class PedidoProductoSerializer(serializers.ModelSerializer):
    """Serializa los productos incluidos en un pedido."""
    class Meta:
        model = PedidoProducto
        fields = ["id", "pedido", "producto", "cantidad", "precio"]

    def validate_cantidad(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor que cero.")
        return value

    def validate_precio(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio no puede ser negativo.")
        return value


class NotificacionSerializer(serializers.ModelSerializer):
    """Las notificaciones se consultan y marcan como leídas, no se reasignan."""
    class Meta:
        model = Notificacion
        fields = ["id", "usuario", "reserva", "mensaje", "leida", "fecha"]
        read_only_fields = ["usuario", "fecha"]
