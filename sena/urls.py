# Rutas URL de la app "sena": define todas las URLs del sistema
# Incluye rutas públicas, de cliente, barbero, admin y API REST
from django.urls import path, include  # Para definir rutas y agrupar URLs
from rest_framework.routers import DefaultRouter  # Router automático para la API REST
from . import views, api  # Vistas (HTML) y API (JSON)

app_name = "sena"  # Namespace para evitar conflictos de nombres entre apps

# Router de DRF: genera automáticamente rutas /api/usuarios/, /api/peluquerias/, etc.
router = DefaultRouter()
router.register(r"usuarios", api.UsuarioViewSet)  # CRUD de usuarios vía API
router.register(r"peluquerias", api.PeluqueriaViewSet)  # CRUD de peluquerías vía API
router.register(r"productos", api.ProductoViewSet)  # CRUD de productos vía API
router.register(r"reservas", api.ReservaViewSet)  # CRUD de reservas vía API

urlpatterns = [
    # === PÁGINAS PÚBLICAS (sin login) ===
    path('', views.inicio, name="inicio"),  # Página principal: redirige según rol o muestra home
    path('login/', views.login, name="login"),  # Formulario de inicio de sesión
    path('recuperar-password/', views.solicitar_recuperacion, name="solicitar_recuperacion"),  # Solicitar enlace de recuperación
    path('restablecer-password/<str:token>/', views.restablecer_password, name="restablecer_password"),  # Formulario con token de recuperación
    path('registro/', views.registro, name="registro"),  # Registro de nuevos clientes
    path('logout/', views.logout, name="logout"),  # Cerrar sesión
    path('como_funciona/', views.como_funciona, name="como_funciona"),  # Página informativa
    path('sobre_nosotros/', views.sobre_nosotros, name="sobre_nosotros"),  # Página institucional
    path('ayuda/', views.ayuda, name="ayuda"),  # Formulario de contacto/soporte

    # === CARRITO DE COMPRAS (funciona sin login) ===
    path('carrito/', views.carrito, name="carrito"),  # Ver el carrito de compras
    path('carrito/agregar/<int:producto_id>/', views.agregar_carrito, name="agregar_carrito"),  # Agregar un producto al carrito
    path('carrito/actualizar/<int:producto_id>/', views.actualizar_carrito, name="actualizar_carrito"),  # Cambiar cantidad de un producto
    path('carrito/eliminar/<int:producto_id>/', views.eliminar_carrito, name="eliminar_carrito"),  # Quitar un producto del carrito
    path('carrito/finalizar/', views.finalizar_pedido, name="finalizar_pedido"),  # Confirmar compra (requiere login)
    path('carrito/pedido_exitoso/<int:pedido_id>/', views.pedido_exitoso, name="pedido_exitoso"),  # Confirmación de pedido

    # === PANEL DEL CLIENTE (requiere rol "Cliente") ===
    path('usuario/dashboard/', views.usuario_dashboard, name="usuario_dashboard"),  # Dashboard del cliente
    path('usuario/tienda/', views.usuario_tienda, name="usuario_tienda"),  # Tienda de productos
    path('usuario/servicios/', views.usuario_servicios, name="usuario_servicios"),  # Lista de servicios de barbería
    path('usuario/peluquerias/', views.usuario_peluquerias, name="usuario_peluquerias"),  # Sedes disponibles
    path('usuario/peluquerias/<int:id>/', views.usuario_peluqueria_detalle, name="usuario_peluqueria_detalle"),  # Detalle de una peluquería
    path('usuario/reservar_cita/', views.usuario_reservar_cita, name="usuario_reservar_cita"),  # Formulario para agendar cita
    path('usuario/pre_confirmar/', views.usuario_pre_confirmar, name="usuario_pre_confirmar"),  # Vista previa antes de confirmar
    path('usuario/confirmar_reserva/', views.usuario_confirmar_reserva, name="usuario_confirmar_reserva"),  # Confirmar la reserva
    path('usuario/perfil/', views.usuario_perfil, name="usuario_perfil"),  # Ver/editar perfil y historial
    path('usuario/cita/<int:reserva_id>/cancelar/', views.usuario_cancelar_reserva, name="usuario_cancelar_reserva"),  # Cancelar una cita
    path('usuario/cita/<int:reserva_id>/editar/', views.usuario_editar_reserva, name="usuario_editar_reserva"),  # Modificar fecha/hora/barbero
    path('usuario/cita/<int:reserva_id>/calificar/', views.usuario_calificar, name="usuario_calificar"),  # Calificar barbero tras cita completada
    path('usuario/notificaciones/', views.usuario_notificaciones, name="usuario_notificaciones"),  # Ver notificaciones
    path('usuario/notificaciones/leidas/', views.usuario_marcar_notificaciones_leidas, name="usuario_marcar_notificaciones_leidas"),  # Marcar todas como leídas
    path('usuario/cita/<int:reserva_id>/confirmar_peluquero/', views.usuario_confirmar_cita_peluquero, name="usuario_confirmar_cita_peluquero"),  # Confirmar cita agendada por barbero
    path('cuenta/cambiar-password/', views.cambiar_password, name="cambiar_password"),  # Cambiar contraseña (cliente o barbero)
    
    # === PANEL DEL BARBERO (requiere rol "Barbero") ===
    path('peluquero/dashboard/', views.peluquero_dashboard, name="peluquero_dashboard"),  # Dashboard: citas, ingresos, calificaciones
    path('peluquero/perfil/', views.peluquero_perfil, name="peluquero_perfil"),  # Ver/editar perfil del barbero
    path('peluquero/crear_cita/', views.peluquero_crear_cita, name="peluquero_crear_cita"),  # Agendar cita para un cliente
    path('peluquero/cita/<int:cita_id>/estado/', views.peluquero_cambiar_estado, name="peluquero_cambiar_estado"),  # Cambiar estado de una cita
    path('peluquero/notificaciones/', views.peluquero_notificaciones, name="peluquero_notificaciones"),  # Ver notificaciones del barbero
    path('peluquero/peluqueria/crear/', views.peluquero_crear_peluqueria, name="peluquero_crear_peluqueria"),  # Crear peluquería (primera vez)
    path('peluquero/peluqueria/editar/', views.peluquero_editar_peluqueria, name="peluquero_editar_peluqueria"),  # Editar mi peluquería
    path('peluquero/galeria/', views.peluquero_galeria, name="peluquero_galeria"),  # Ver galería de fotos
    path('peluquero/galeria/agregar/', views.peluquero_agregar_imagen, name="peluquero_agregar_imagen"),  # Subir foto
    path('peluquero/galeria/<int:imagen_id>/eliminar/', views.peluquero_eliminar_imagen, name="peluquero_eliminar_imagen"),  # Eliminar foto
    
    # === PANEL DEL ADMINISTRADOR (requiere rol "Admin") ===
    path('admin/dashboard/', views.admin_dashboard, name="admin_dashboard"),  # Dashboard: métricas y ventas
    path('admin/usuarios/', views.admin_usuarios, name="admin_usuarios"),  # Listar todos los usuarios
    path('admin/crear_usuario/', views.admin_crear_usuario, name="admin_crear_usuario"),  # Crear usuario nuevo
    path('admin/editar_usuario/<int:id>/', views.admin_editar_usuario, name="admin_editar_usuario"),  # Editar datos de usuario
    path('admin/eliminar_usuario/<int:id>/', views.admin_eliminar_usuario, name="admin_eliminar_usuario"),  # Suspender usuario
    path('admin/suspender_usuario/<int:id>/', views.admin_suspender_usuario, name="admin_suspender_usuario"),  # Activar/desactivar usuario
    path('admin/peluqueros/', views.admin_peluqueros, name="admin_peluqueros"),  # Listar barberos
    path('admin/crear_peluquero/', views.admin_crear_peluquero, name="admin_crear_peluquero"),  # Crear barbero nuevo
    path('admin/editar_peluquero/<int:id>/', views.admin_editar_peluquero, name="admin_editar_peluquero"),  # Editar barbero
    path('admin/eliminar_peluquero/<int:id>/', views.admin_eliminar_peluquero, name="admin_eliminar_peluquero"),  # Suspender barbero
    path('admin/reservas/', views.admin_reservas, name="admin_reservas"),  # Listar todas las reservas
    path('admin/crear_reserva/', views.admin_crear_reserva, name="admin_crear_reserva"),  # Crear reserva manual
    path('admin/editar_reserva/<int:id>/', views.admin_editar_reserva, name="admin_editar_reserva"),  # Editar reserva existente
    path('admin/eliminar_reserva/<int:id>/', views.admin_eliminar_reserva, name="admin_eliminar_reserva"),  # Eliminar reserva
    path('admin/cancelar_reserva/<int:id>/', views.admin_cancelar_reserva, name="admin_cancelar_reserva"),  # Cancelar reserva sin eliminar
    path('admin/ingresos/', views.admin_ingresos, name="admin_ingresos"),  # Historial de inicios de sesión
    path('admin/perfil/', views.admin_perfil, name="admin_perfil"),  # Perfil del admin
    path('admin/horarios/', views.admin_horarios, name="admin_horarios"),  # Gestionar horarios y bloqueos
    path('admin/eliminar_bloqueo/<int:id>/', views.admin_eliminar_bloqueo, name="admin_eliminar_bloqueo"),  # Quitar un bloqueo de horario
    path('admin/peluquerias/', views.admin_peluquerias, name="admin_peluquerias"),  # Listar sedes
    path('admin/peluquerias/nueva/', views.admin_crear_peluqueria, name="admin_crear_peluqueria"),  # Crear sede nueva
    path('admin/peluquerias/<int:id>/editar/', views.admin_editar_peluqueria, name="admin_editar_peluqueria"),  # Editar sede
    path('admin/peluquerias/<int:id>/eliminar/', views.admin_eliminar_peluqueria, name="admin_eliminar_peluqueria"),  # Eliminar sede
    path('admin/productos/', views.admin_productos, name="admin_productos"),  # Listar productos
    path('admin/productos/nuevo/', views.admin_crear_producto, name="admin_crear_producto"),  # Crear producto nuevo
    path('admin/productos/<int:id>/editar/', views.admin_editar_producto, name="admin_editar_producto"),  # Editar producto
    path('admin/productos/<int:id>/eliminar/', views.admin_eliminar_producto, name="admin_eliminar_producto"),  # Retirar producto de la tienda
    path('admin/mensajes/', views.admin_mensajes, name="admin_mensajes"),  # Ver mensajes de contacto
    path('admin/notificaciones/', views.admin_notificaciones, name="admin_notificaciones"),  # Ver notificaciones del admin

    # === API REST (accesible con token o sesión) ===
    path('api/', include(router.urls)),  # Incluye las rutas del router de DRF
]
