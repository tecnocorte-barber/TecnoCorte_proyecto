# Registro de los modelos en el panel de administración de Django
# Cada clase define qué columnas, filtros y búsquedas se muestran en el admin
from django.contrib import admin
from .models import (
    Usuario, Peluqueria, Producto, Reserva, Pedido,
    PedidoProducto, RegistroIngreso, Notificacion,
    HorarioTrabajo, BloqueoHorario, MensajeContacto, Calificacion,
)


# Admin de usuarios: gestiona cuentas, roles y estado activo (oculta la contraseña)
@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "apellido", "email", "rol", "telefono", "activo", "fecha_creacion")
    list_filter = ("rol", "activo")
    search_fields = ("nombre", "apellido", "email")
    list_editable = ("activo",)
    exclude = ("password",)


# Admin de peluquerías: sedes con su ubicación y teléfono
@admin.register(Peluqueria)
class PeluqueriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "ubicacion", "telefono")
    search_fields = ("nombre",)


# Admin de productos: catálogo de la tienda con precio, stock y disponibilidad
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "precio", "categoria", "stock", "disponible")
    list_filter = ("categoria", "disponible")
    search_fields = ("nombre",)


# Admin de reservas: citas de clientes con peluqueros, fecha, hora y estado
@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "peluquero", "peluqueria", "fecha", "hora", "servicio", "estado")
    list_filter = ("estado", "fecha")


# Admin de pedidos: compras realizadas por los clientes
@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "total", "estado", "fecha")
    list_filter = ("estado",)


# Admin del detalle de pedidos: productos y cantidades de cada compra
@admin.register(PedidoProducto)
class PedidoProductoAdmin(admin.ModelAdmin):
    list_display = ("pedido", "producto", "cantidad", "precio")


# Admin de registros de ingreso: historial de inicios de sesión con IP
@admin.register(RegistroIngreso)
class RegistroIngresoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "rol", "fecha", "ip")


# Admin de notificaciones: mensajes enviados a los usuarios
@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ("usuario", "mensaje", "leida", "fecha")
    list_filter = ("leida",)


# Admin de horarios de trabajo: días y horas de atención de cada sede
@admin.register(HorarioTrabajo)
class HorarioTrabajoAdmin(admin.ModelAdmin):
    list_display = ("peluqueria", "get_dia_semana_display", "activo", "hora_inicio", "hora_fin")
    list_filter = ("peluqueria",)


# Admin de bloqueos de horario: franjas no disponibles por motivos especiales
@admin.register(BloqueoHorario)
class BloqueoHorarioAdmin(admin.ModelAdmin):
    list_display = ("peluqueria", "fecha", "hora", "motivo")
    list_filter = ("peluqueria",)


# Admin de mensajes de contacto: consultas enviadas desde el formulario web
@admin.register(MensajeContacto)
class MensajeContactoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "email", "asunto", "fecha", "leido")
    list_filter = ("leido",)


# Admin de calificaciones: puntuaciones que los clientes dan a los barberos
@admin.register(Calificacion)
class CalificacionAdmin(admin.ModelAdmin):
    list_display = ("cliente", "barbero", "puntuacion", "fecha")
    list_filter = ("puntuacion",)
