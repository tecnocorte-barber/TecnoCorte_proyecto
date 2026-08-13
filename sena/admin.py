from django.contrib import admin
from .models import Peluqueria, Producto, Reserva, Pedido, PedidoProducto, RegistroIngreso

admin.site.register(Peluqueria)
admin.site.register(Producto)
admin.site.register(Reserva)
admin.site.register(Pedido)
admin.site.register(PedidoProducto)
admin.site.register(RegistroIngreso)
