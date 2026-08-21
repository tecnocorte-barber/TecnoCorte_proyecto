from django.contrib import admin
from .models import (
    Usuario, Peluqueria, Producto, Reserva, Pedido,
    PedidoProducto, RegistroIngreso, Notificacion,
    HorarioTrabajo, BloqueoHorario, MensajeContacto, Calificacion,
)


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "apellido", "email", "rol", "telefono", "activo", "fecha_creacion")
    list_filter = ("rol", "activo")
    search_fields = ("nombre", "apellido", "email")
    list_editable = ("activo",)
    exclude = ("password",)


@admin.register(Peluqueria)
class PeluqueriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "ubicacion", "telefono")
    search_fields = ("nombre",)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "precio", "categoria", "stock", "disponible")
    list_filter = ("categoria", "disponible")
    search_fields = ("nombre",)


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "peluquero", "peluqueria", "fecha", "hora", "servicio", "estado")
    list_filter = ("estado", "fecha")


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "total", "estado", "fecha")
    list_filter = ("estado",)


@admin.register(PedidoProducto)
class PedidoProductoAdmin(admin.ModelAdmin):
    list_display = ("pedido", "producto", "cantidad", "precio")


@admin.register(RegistroIngreso)
class RegistroIngresoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "rol", "fecha", "ip")


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ("usuario", "mensaje", "leida", "fecha")
    list_filter = ("leida",)


@admin.register(HorarioTrabajo)
class HorarioTrabajoAdmin(admin.ModelAdmin):
    list_display = ("peluqueria", "get_dia_semana_display", "activo", "hora_inicio", "hora_fin")
    list_filter = ("peluqueria",)


@admin.register(BloqueoHorario)
class BloqueoHorarioAdmin(admin.ModelAdmin):
    list_display = ("peluqueria", "fecha", "hora", "motivo")
    list_filter = ("peluqueria",)


@admin.register(MensajeContacto)
class MensajeContactoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "email", "asunto", "fecha", "leido")
    list_filter = ("leido",)


@admin.register(Calificacion)
class CalificacionAdmin(admin.ModelAdmin):
    list_display = ("cliente", "barbero", "puntuacion", "fecha")
    list_filter = ("puntuacion",)
