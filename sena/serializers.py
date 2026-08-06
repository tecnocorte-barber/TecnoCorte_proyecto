from rest_framework import serializers
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
        return Usuario.objects.create(**validated_data)


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
    peluquero = serializers.PrimaryKeyRelatedField(queryset=Usuario.objects.filter(rol="Peluquero"))
    cliente_nombre = serializers.SerializerMethodField()
    peluquero_nombre = serializers.SerializerMethodField()
    peluqueria_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Reserva
        fields = [
            "id", "cliente", "peluquero", "peluqueria",
            "cliente_nombre", "peluquero_nombre", "peluqueria_nombre",
            "fecha", "hora", "estado",
        ]
        extra_kwargs = {
            "peluqueria": {"write_only": True},
        }

    def validate_cliente(self, value):
        if value.rol != "Cliente":
            raise serializers.ValidationError("El cliente debe tener rol Cliente.")
        return value

    def validate_peluquero(self, value):
        if value.rol != "Peluquero":
            raise serializers.ValidationError("El peluquero debe tener rol Peluquero.")
        return value

    def get_cliente_nombre(self, obj):
        return f"{obj.cliente.nombre} {obj.cliente.apellido}"

    def get_peluquero_nombre(self, obj):
        return f"{obj.peluquero.nombre} {obj.peluquero.apellido}"

    def get_peluqueria_nombre(self, obj):
        return obj.peluqueria.nombre
