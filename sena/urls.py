from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views, api

app_name = "sena"

router = DefaultRouter()
router.register(r"usuarios", api.UsuarioViewSet)
router.register(r"peluquerias", api.PeluqueriaViewSet)
router.register(r"productos", api.ProductoViewSet)
router.register(r"reservas", api.ReservaViewSet)

urlpatterns = [
    path('', views.inicio, name="inicio"),
    path('login/', views.login, name="login"),
    path('registro/', views.registro, name="registro"),
    path('logout/', views.logout, name="logout"),
    path('como_funciona/', views.como_funciona, name="como_funciona"),
    path('sobre_nosotros/', views.sobre_nosotros, name="sobre_nosotros"),
    path('ayuda/', views.ayuda, name="ayuda"),

    path('carrito/', views.carrito, name="carrito"),
    path('carrito/agregar/<int:producto_id>/', views.agregar_carrito, name="agregar_carrito"),
    path('carrito/actualizar/<int:producto_id>/', views.actualizar_carrito, name="actualizar_carrito"),
    path('carrito/eliminar/<int:producto_id>/', views.eliminar_carrito, name="eliminar_carrito"),
    path('carrito/finalizar/', views.finalizar_pedido, name="finalizar_pedido"),
    path('carrito/pedido_exitoso/<int:pedido_id>/', views.pedido_exitoso, name="pedido_exitoso"),

    path('usuario/dashboard/', views.usuario_dashboard, name="usuario_dashboard"),
    path('usuario/tienda/', views.usuario_tienda, name="usuario_tienda"),
    path('usuario/servicios/', views.usuario_servicios, name="usuario_servicios"),
    path('usuario/peluquerias/', views.usuario_peluquerias, name="usuario_peluquerias"),
    path('usuario/reservar_cita/', views.usuario_reservar_cita, name="usuario_reservar_cita"),
    path('usuario/pre_confirmar/', views.usuario_pre_confirmar, name="usuario_pre_confirmar"),
    path('usuario/confirmar_reserva/', views.usuario_confirmar_reserva, name="usuario_confirmar_reserva"),
    path('usuario/perfil/', views.usuario_perfil, name="usuario_perfil"),
    path('usuario/cita/<int:reserva_id>/cancelar/', views.usuario_cancelar_reserva, name="usuario_cancelar_reserva"),
    path('usuario/cita/<int:reserva_id>/editar/', views.usuario_editar_reserva, name="usuario_editar_reserva"),
    path('usuario/cita/<int:reserva_id>/calificar/', views.usuario_calificar, name="usuario_calificar"),
    
    path('peluquero/dashboard/', views.peluquero_dashboard, name="peluquero_dashboard"),
    path('peluquero/perfil/', views.peluquero_perfil, name="peluquero_perfil"),
    path('peluquero/crear_cita/', views.peluquero_crear_cita, name="peluquero_crear_cita"),
    path('peluquero/cita/<int:cita_id>/estado/', views.peluquero_cambiar_estado, name="peluquero_cambiar_estado"),
    path('peluquero/notificaciones/', views.peluquero_notificaciones, name="peluquero_notificaciones"),
    
    path('admin/dashboard/', views.admin_dashboard, name="admin_dashboard"),
    path('admin/usuarios/', views.admin_usuarios, name="admin_usuarios"),
    path('admin/crear_usuario/', views.admin_crear_usuario, name="admin_crear_usuario"),
    path('admin/editar_usuario/<int:id>/', views.admin_editar_usuario, name="admin_editar_usuario"),
    path('admin/eliminar_usuario/<int:id>/', views.admin_eliminar_usuario, name="admin_eliminar_usuario"),
    path('admin/suspender_usuario/<int:id>/', views.admin_suspender_usuario, name="admin_suspender_usuario"),
    path('admin/peluqueros/', views.admin_peluqueros, name="admin_peluqueros"),
    path('admin/crear_peluquero/', views.admin_crear_peluquero, name="admin_crear_peluquero"),
    path('admin/editar_peluquero/<int:id>/', views.admin_editar_peluquero, name="admin_editar_peluquero"),
    path('admin/eliminar_peluquero/<int:id>/', views.admin_eliminar_peluquero, name="admin_eliminar_peluquero"),
    path('admin/reservas/', views.admin_reservas, name="admin_reservas"),
    path('admin/crear_reserva/', views.admin_crear_reserva, name="admin_crear_reserva"),
    path('admin/editar_reserva/<int:id>/', views.admin_editar_reserva, name="admin_editar_reserva"),
    path('admin/eliminar_reserva/<int:id>/', views.admin_eliminar_reserva, name="admin_eliminar_reserva"),
    path('admin/cancelar_reserva/<int:id>/', views.admin_cancelar_reserva, name="admin_cancelar_reserva"),
    path('admin/ingresos/', views.admin_ingresos, name="admin_ingresos"),
    path('admin/perfil/', views.admin_perfil, name="admin_perfil"),
    path('admin/horarios/', views.admin_horarios, name="admin_horarios"),
    path('admin/eliminar_bloqueo/<int:id>/', views.admin_eliminar_bloqueo, name="admin_eliminar_bloqueo"),
    path('admin/peluquerias/', views.admin_peluquerias, name="admin_peluquerias"),
    path('admin/peluquerias/nueva/', views.admin_crear_peluqueria, name="admin_crear_peluqueria"),
    path('admin/peluquerias/<int:id>/editar/', views.admin_editar_peluqueria, name="admin_editar_peluqueria"),
    path('admin/peluquerias/<int:id>/eliminar/', views.admin_eliminar_peluqueria, name="admin_eliminar_peluqueria"),
    path('admin/productos/', views.admin_productos, name="admin_productos"),
    path('admin/productos/nuevo/', views.admin_crear_producto, name="admin_crear_producto"),
    path('admin/productos/<int:id>/editar/', views.admin_editar_producto, name="admin_editar_producto"),
    path('admin/productos/<int:id>/eliminar/', views.admin_eliminar_producto, name="admin_eliminar_producto"),
    path('admin/mensajes/', views.admin_mensajes, name="admin_mensajes"),

    path('api/', include(router.urls)),
]
