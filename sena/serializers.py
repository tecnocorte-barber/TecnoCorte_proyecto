from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from .models import Usuario, Peluqueria, Producto, Reserva


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "nombre", "apellido", "email", "password", "telefono", "rol", "fecha_creacion"]
        extra_kwargs = {
            "password": {"write_only": True},
            "fecha_creacion": {"read_only": True},
        }

    def create(self, validated_data):
        validated_data["password"] = make_password(validated_data["password"])
        return Usuario.objects.create(**validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            instance.password = make_password(password)
        return super().update(instance, validated_data)


class PeluqueriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Peluqueria
        fields = "__all__"


class ProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = "__all__"


class ReservaSerializer(serializers.ModelSerializer):
    cliente = serializers.PrimaryKeyRelatedField(queryset=Usuario.objects.filter(rol="Cliente"))
    peluquero = serializers.PrimaryKeyRelatedField(queryset=Usuario.objects.filter(rol="Barbero"))
    cliente_nombre = serializers.SerializerMethodField()
    peluquero_nombre = serializers.SerializerMethodField()
    peluqueria_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Reserva
        fields = [
            "id", "cliente", "peluquero", "peluqueria",
            "cliente_nombre", "peluquero_nombre", "peluqueria_nombre",
            "fecha", "hora", "estado",
            "servicio",
        ]
        extra_kwargs = {
            "peluqueria": {"write_only": True},
        }

    def validate_servicio(self, value):
        from .views import SERVICIOS
        if value not in {item["nombre"] for item in SERVICIOS}:
            raise serializers.ValidationError("El servicio seleccionado no es válido.")
        return value

    def validate_cliente(self, value):
        if value.rol != "Cliente":
            raise serializers.ValidationError("El cliente debe tener rol Cliente.")
        return value

    def validate_peluquero(self, value):
        if value.rol != "Barbero":
            raise serializers.ValidationError("El barbero debe tener rol Barbero.")
        return value

    def get_cliente_nombre(self, obj) -> str:
        return f"{obj.cliente.nombre} {obj.cliente.apellido}"

    def get_peluquero_nombre(self, obj) -> str:
        return f"{obj.peluquero.nombre} {obj.peluquero.apellido}"

    def get_peluqueria_nombre(self, obj) -> str:
        return obj.peluqueria.nombre
