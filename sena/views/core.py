# Vistas principales de TecnoCorte: toda la lógica de las páginas web
# Incluye: autenticación, carrito, reservas, paneles de cliente/barbero/admin, y más
import json  # Para serializar horarios y reservas a JSON para JavaScript
import hmac  # Para comparar tokens de forma segura (recuperación de contraseña)
import hashlib
import secrets

from django.shortcuts import render, redirect, get_object_or_404  # Renderizar plantillas, redirigir, buscar objeto o 404
from django.urls import reverse  # Generar URLs por nombre
from django.http import HttpResponse, JsonResponse  # Respuestas HTTP y JSON
from django.utils import timezone  # Hora actual con zona horaria
from django.db import IntegrityError, models, transaction  # Errores de BD, agregaciones y transacciones
from django.db.models import Count, Q  # Agregaciones y filtros condicionales (Consultas optimizadas)
from django.contrib.auth.hashers import check_password, make_password  # Verificar y cifrar contraseñas
from django.contrib import messages  # Mensajes flash para el usuario
from django.conf import settings  # Configuración del proyecto (email, etc.)
from django.core import signing  # Firma encriptada para tokens de recuperación
from django.core.signing import salted_hmac  # HMAC con sal para tokens seguros
from django.utils.http import url_has_allowed_host_and_scheme  # Validar URLs de redirección (seguridad)
from django.core.cache import cache  # Cache para rate limiting (anti fuerza bruta)
from django.core.validators import validate_email  # Validar formato de correo
from django.core.exceptions import ValidationError  # Excepciones de validación
from django.db.models.deletion import ProtectedError  # Relaciones protegidas al eliminar usuarios
from datetime import datetime, time, timedelta  # Manejo de fechas, horas y duraciones
from html import escape  # Escapa valores al generar reportes HTML compatibles con Excel
from ..models import Usuario, Peluqueria, ImagenPeluqueria, Producto, Reserva, Pedido, PedidoProducto, RegistroIngreso, Notificacion, HorarioTrabajo, BloqueoHorario, MensajeContacto, Calificacion, Configuracion, Servicio, SolicitudServicio, TIPOS_MENSAJE, TIPOS_MENSAJE_DICCIONARIO  # Todos los modelos
from ..utilidades import autorizacion, validar_password, validar_telefono, validar_imagen, registrar_accion, transicion_valida, TRANSICIONES_RESERVA, TRANSICIONES_PEDIDO  # Seguridad, auditoría, estados y validación
from ..context_processors import carrito_visible, guardar_carrito_activo, cargar_carrito_usuario  # Funciones del carrito por sesión
from ..services.correos import enviar_correo, enviar_correo_destino, enviar_correo_cita
from ..services.catalogo import SERVICIOS, DURACIONES_SERVICIO, catalogo_servicios, servicio_valido, minutos_servicio
from ..services.disponibilidad import cita_disponible, barberos_disponibles, formato_cita, barbero_esta_disponible
from ..services.autenticacion import token_recuperacion, usuario_desde_token, crear_codigo_verificacion as _crear_codigo_verificacion, enviar_codigo_verificacion as _enviar_codigo_verificacion

# Imagen de respaldo para las tarjetas del inicio. En los servicios se elige por
# nombre y en los productos por categoría, porque pueden no tener foto propia.
IMAGENES_SERVICIO = {
    "Corte de Cabello": "sena/images/corte_cabello.jpeg",
    "Arreglo de Barba": "sena/images/arreglo_barba.jpeg",
    "Combo Completo": "sena/images/servicio_completo.jpeg",
}
IMAGEN_SERVICIO_POR_DEFECTO = "sena/images/corte_masculino.jpg"
IMAGENES_PRODUCTO = {
    "Herramientas": "sena/images/maquina_motilar.jpg",
    "Fijacion": "sena/images/pomada_barba.jpeg",
    "Cuidado": "sena/images/cepillo.jpeg",
    "Barba": "sena/images/aceite_barba.jpeg",
}
IMAGEN_PRODUCTO_POR_DEFECTO = "sena/images/pomada_barba.jpeg"

# Cuántas reseñas se muestran en el inicio antes de ofrecer "Ver más".
# Productos que la portada destaca mientras el Admin no elija otros: son la
# pomada y el aceite de siempre. Se buscan por nombre en el catálogo real, igual
# que los servicios base de SERVICIOS.
PRODUCTOS_DESTACADOS_POR_DEFECTO = ["Pomada para el Cabello", "Aceite para Barba"]

RESENAS_VISIBLES = 5

# Convierte los horarios de trabajo y bloqueos a JSON para que JavaScript los use en el calendario
def _horarios_para_template(peluqueria_id=None):
    clave = f"horarios_json_{peluqueria_id or 'todas'}"  # Clave de caché por peluquería
    datos = cache.get(clave)
    if datos is None:
        horarios = {}  # Diccionario: {peluqueria_id: {dia: {activo, inicio, fin}}}
        for h in HorarioTrabajo.objects.all().only("peluqueria_id", "dia_semana", "activo", "hora_inicio", "hora_fin"):  # Recorre todos los horarios configurados
            pid = str(h.peluqueria_id)  # ID de la peluquería como string
            if pid not in horarios:
                horarios[pid] = {}  # Inicializa el diccionario para esa peluquería
            horarios[pid][h.dia_semana] = {"activo": h.activo, "inicio": h.hora_inicio.strftime("%H:%M"), "fin": h.hora_fin.strftime("%H:%M")}
        bloqueos = []  # Lista de fechas/horas bloqueadas
        qs = BloqueoHorario.objects.all()  # Query de todos los bloqueos
        if peluqueria_id:
            qs = qs.filter(peluqueria_id=peluqueria_id)  # Filtra por peluquería si se indica
        for b in qs:
            bloqueos.append({"fecha": b.fecha.strftime("%Y-%m-%d"), "hora": b.hora.strftime("%H:%M") if b.hora else None})
        datos = {
            "horarios_json": _json_seguro(horarios),  # Horarios seguros para JavaScript
            "bloqueos_json": _json_seguro(bloqueos),  # Bloqueos seguros para JavaScript
        }
        cache.set(clave, datos, 15)  # TTL corto: los horarios cambian poco
    ahora = timezone.localtime()  # Hora actual del servidor (siempre fresca)
    return {
        **datos,
        "fecha_hoy": ahora.date().isoformat(),  # Fecha de hoy en formato ISO
        "hora_actual": ahora.strftime("%H:%M"),  # Hora actual en formato HH:MM
    }


# Invalida las cachés cortas de disponibilidad cuando cambian horarios, bloqueos o citas
def _invalidar_cache_disponibilidad():
    for clave in ("reservas_json", "horarios_json_todas"):
        cache.delete(clave)


# Borra el archivo de un ImageField sin tocar el registro. Tolera valores antiguos
# que eran URLs (antes de que los productos usaran archivos subidos).
def _borrar_archivo(campo):
    if not campo:
        return
    try:
        campo.delete(save=False)
    except Exception:
        pass


# Convierte las reservas existentes a JSON para que JavaScript evite mostrar horarios ocupados
def _reservas_para_template():
    datos = cache.get("reservas_json")
    if datos is None:
        reservas = []
        for reserva in Reserva.objects.exclude(estado="Cancelada").only("peluquero_id", "fecha", "hora", "servicio"):  # Solo las no canceladas
            reservas.append({
                "barbero": reserva.peluquero_id,  # ID del barbero
                "fecha": reserva.fecha.isoformat(),  # Fecha en formato ISO
                "hora": reserva.hora.strftime("%H:%M"),  # Hora en formato HH:MM
                "minutos": minutos_servicio(reserva.servicio),  # Duración del servicio
            })
        datos = {"reservas_json": _json_seguro(reservas)}  # Reservas seguras para JavaScript
        cache.set("reservas_json", datos, 10)  # TTL corto: refleja citas nuevas con rapidez
    return datos


def _json_seguro(valor):
    """Serializa a JSON a prueba de cierre de etiqueta.

    Se usa con el filtro |safe dentro de <script>. json.dumps no escapa "<",
    ">", "&" ni los separadores de línea de Unicode: con un solo texto libre en
    los datos (por ejemplo el motivo de un bloqueo) bastaría "</script>" para
    inyectar código. Se escapan como \u003c, que JavaScript interpreta igual.
    """
    return (
        json.dumps(valor, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


# Convierte un valor a entero o devuelve None si no es válido (previene inyección)
def _id_entero(valor):
    try:
        valor = str(valor or "").strip()  # Convierte a string y limpia espacios
        return int(valor) if valor.isdigit() else None  # Solo acepta dígitos puros
    except (TypeError, ValueError):
        return None  # Si falla, devuelve None

# Construye el contexto del carrito: lista de items, total y cantidad
def contexto_carrito(request):
    carrito = request.session.get("carrito", {}) if carrito_visible(request) else {}  # Obtiene carrito de la sesión
    items = []  # Lista de productos en el carrito
    total = 0  # Suma total del carrito
    cantidad = 0  # Total de unidades
    # Una sola consulta para todos los productos del carrito (evita N+1 con la BD remota)
    ids = [int(pid) for pid in carrito if str(pid).isdigit()]
    productos = Producto.objects.in_bulk(ids) if ids else {}
    for producto_id, cantidad_item in carrito.items():  # Recorre cada producto del carrito
        if not str(producto_id).isdigit():
            continue
        producto = productos.get(int(producto_id))  # Producto ya cargado en memoria
        if producto is None:
            continue  # Si no existe, lo omite
        try:
            cantidad_item = int(cantidad_item)
        except (TypeError, ValueError):
            continue
        subtotal = producto.precio * cantidad_item  # Precio unitario * cantidad
        total += subtotal  # Acumula al total
        cantidad += cantidad_item  # Acumula unidades
        items.append({
            "producto": producto,  # Objeto producto completo
            "cantidad": cantidad_item,  # Unidades de este producto
            "subtotal": subtotal,  # Subtotal de este producto
        })
    return {
        "items": items,  # Lista de items para el template
        "total": total,  # Total del carrito
        "cantidad": cantidad,  # Cantidad total de unidades
        "carrito": carrito,  # Carrito crudo de la sesión
        "mensaje_tienda": request.session.pop("mensaje_tienda", ""),  # Mensaje pendiente de la tienda (se borra al leer)
        "mensaje_carrito": request.session.pop("mensaje_carrito", ""),  # Mensaje pendiente del carrito (se borra al leer)
    }

# Registra cada inicio de sesión en la tabla de historial
def registrar_ingreso(request, usuario):
    ip = request.META.get("REMOTE_ADDR", "")  # IP del cliente (puede venir de proxy)
    RegistroIngreso.objects.create(usuario=usuario, rol=usuario.rol, ip=ip)  # Guarda el registro


# Verifica si una fecha/hora está disponible para agendar una cita


# Avisa a todos los Admin activos de un evento (una sola inserción)
def notificar_admins(mensaje):
    admins = list(Usuario.objects.filter(rol="Admin", activo=True).only("id"))
    if admins:
        Notificacion.objects.bulk_create(
            [Notificacion(usuario=admin, mensaje=mensaje, fecha=timezone.now()) for admin in admins]
        )




# Formatea la fecha y hora de una reserva para mostrar en notificaciones y correos


# Salt para generar tokens de recuperación de contraseña (evita que se adivinen)
RESET_SALT = "tecnocorte-password-reset"


# Genera un token firmado para recuperar la contraseña (válido 1 hora)


# Valida un token de recuperación y devuelve el usuario si es válido










# Notifica a los clientes cuando se suspende un barbero, dejando sus citas pendientes para reagendar
def notificar_suspension_barbero(request, barbero):
    """Deja las citas futuras pendientes para que el cliente pueda reasignarlas."""
    ahora = timezone.localtime()  # Hora actual
    reservas = Reserva.objects.select_related("cliente").filter(  # Busca citas futuras del barbero
        peluquero=barbero,
        fecha__gte=ahora.date(),  # Solo fechas de hoy en adelante
    ).exclude(estado__in=["Cancelada", "Completada"])  # Excluye canceladas y completadas
    for reserva in reservas:
        if reserva.fecha == ahora.date() and reserva.hora <= ahora.time().replace(second=0, microsecond=0):
            continue  # Salta citas de hoy que ya pasaron
        if reserva.estado != "Pendiente":
            reserva.estado = "Pendiente"  # Pone la cita en pendiente
            reserva.save(update_fields=["estado"])
        momento = formato_cita(reserva)  # Fecha/hora legible
        mensaje = (
            f"Tu barbero fue suspendido y no podrá atenderte el {momento}. "
            "Puedes reagendar la cita con otro barbero desde el enlace de modificación."
        )
        Notificacion.objects.create(usuario=reserva.cliente, reserva=reserva, mensaje=mensaje)  # Crea notificación
        enviar_correo_cita(  # Envía correo al cliente
            request,
            reserva.cliente,
            "Necesitas reagendar tu cita en TecnoCorte",
            f"Hola {reserva.cliente.nombre},\n\n{mensaje}",
            request.build_absolute_uri(reverse("sena:usuario_editar_reserva", args=[reserva.id])),  # Enlace para editar
        )


# Verifica que el barbero no tenga otra cita que se cruce con el horario propuesto

# INICIO - Sin login
def contenido_inicio():
    """Servicios, productos y reseñas que se muestran en la página principal.

    El Admin elige qué dos servicios y qué dos productos se destacan. Si deja
    alguno sin elegir, la portada usa los de siempre (los primeros servicios del
    catálogo y la pomada con el aceite) para que nunca quede con huecos.
    """
    config = Configuracion.cargar()

    # â”€â”€ Servicios destacados â”€â”€
    catalogo = catalogo_servicios()
    por_nombre = {s["nombre"]: s for s in catalogo}
    elegidos = []
    for nombre in (config.servicio_destacado_1, config.servicio_destacado_2):
        if nombre and nombre in por_nombre and nombre not in {e["nombre"] for e in elegidos}:
            elegidos.append(por_nombre[nombre])
    for servicio in catalogo:  # Completa hasta dos, sin repetir
        if len(elegidos) >= 2:
            break
        if servicio["nombre"] not in {e["nombre"] for e in elegidos}:
            elegidos.append(servicio)
    inicio_servicios = [
        {**s, "imagen": IMAGENES_SERVICIO.get(s["nombre"], IMAGEN_SERVICIO_POR_DEFECTO)}
        for s in elegidos[:2]
    ]

    # â”€â”€ Productos destacados â”€â”€
    productos = []
    for producto in (config.producto_destacado_1, config.producto_destacado_2):
        if producto and producto.disponible and producto.id not in {p.id for p in productos}:
            productos.append(producto)
    if len(productos) < 2:
        # Primero los de siempre (pomada y aceite, en ese orden); si ya no
        # existen, se completa con los primeros productos disponibles.
        de_siempre = list(
            Producto.objects.filter(disponible=True, nombre__in=PRODUCTOS_DESTACADOS_POR_DEFECTO)
        )
        de_siempre.sort(key=lambda p: PRODUCTOS_DESTACADOS_POR_DEFECTO.index(p.nombre))
        candidatos = de_siempre + list(Producto.objects.filter(disponible=True).order_by("id"))
        for producto in candidatos:
            if len(productos) >= 2:
                break
            if producto.id not in {p.id for p in productos}:
                productos.append(producto)
    for producto in productos:
        # Respaldo de imagen por categoría (los productos pueden no tener foto).
        producto.imagen_respaldo = IMAGENES_PRODUCTO.get(
            producto.categoria, IMAGEN_PRODUCTO_POR_DEFECTO
        )

    # â”€â”€ Reseñas reales: solo se publican si el Admin lo permite â”€â”€
    resenas = []
    if config.mostrar_calificaciones:
        resenas = list(
            Calificacion.objects.select_related("cliente", "barbero").all()[:60]
        )

    return {
        "inicio_servicios": inicio_servicios,
        "inicio_productos": productos[:2],
        "inicio_resenas": resenas,
        "resenas_visibles": RESENAS_VISIBLES,
    }


def inicio(request):
    # El Admin y el Barbero trabajan en su panel, pero el Admin puede abrir el
    # inicio con ?vista=publica para revisarlo o usar el botón "Editar inicio".
    if request.session.get("logueado") and request.GET.get("vista") != "publica":
        rol = request.session["logueado"]["rol"]
        if rol == "Admin":
            return redirect("sena:admin_dashboard")
        elif rol == "Barbero":
            return redirect("sena:peluquero_dashboard")
    contexto = contexto_carrito(request)
    contexto.update(contenido_inicio())
    return render(request, "publicos/index.html", contexto)




# LOGIN





# LOGOUT

# REGISTRO DE CLIENTES
def como_funciona(request):
    return render(request, "publicos/como_funciona.html")

def sobre_nosotros(request):
    return render(request, "publicos/sobre_nosotros.html")


def politicas(request):
    """Políticas de Privacidad y del Proyecto (enlace en el pie de página)."""
    return render(request, "publicos/politicas.html", contexto_carrito(request))


def health_check(request):
    """Endpoint mínimo para monitores de disponibilidad y proveedores cloud."""
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ZONA DE CONFIGURACIÃ“N (cliente y barbero)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

PESTANAS_CONFIG_USUARIO = ("perfil", "seguridad", "notificaciones", "privacidad")
PESTANAS_CONFIG_PELUQUERO = ("portafolio", "agenda", "servicios", "notificaciones")


def _pestanas_config(request, permitidas):
    """Devuelve la pestaña de configuración pedida en ?seccion= (o la primera)."""
    seccion = (request.GET.get("seccion") or permitidas[0]).strip().lower()
    return seccion if seccion in permitidas else permitidas[0]


def _datos_notificacion(request, usuario):
    """Aplica los cambios de notificaciones del formulario y los guarda."""
    usuario.aviso_correo = request.POST.get("correo") == "on"
    usuario.aviso_whatsapp = request.POST.get("whatsapp") == "on"
    usuario.aviso_sms = request.POST.get("sms") == "on"
    try:
        usuario.aviso_anticipacion_horas = max(1, int(request.POST.get("anticipacion", 24)))
    except (TypeError, ValueError):
        usuario.aviso_anticipacion_horas = 24
    usuario.save(update_fields=["aviso_correo", "aviso_whatsapp", "aviso_sms", "aviso_anticipacion_horas"])


def _datos_descargables(usuario):
    """Exporta los datos personales del usuario en un JSON descargable."""
    reservas = Reserva.objects.select_related("peluqueria").filter(cliente=usuario).order_by("-fecha")[:100]
    pedidos = Pedido.objects.filter(cliente=usuario).prefetch_related("productos__producto").order_by("-fecha")[:100]
    mensajes = MensajeContacto.objects.filter(email=usuario.email).order_by("-fecha")[:100]
    return {
        "perfil": {
            "nombre": usuario.nombre,
            "apellido": usuario.apellido,
            "email": usuario.email,
            "telefono": usuario.telefono,
            "rol": usuario.rol,
            "fecha_registro": usuario.fecha_creacion.strftime("%Y-%m-%d %H:%M") if usuario.fecha_creacion else None,
        },
        "reservas": [
            {
                "peluqueria": r.peluqueria.nombre if r.peluqueria else "",
                "fecha": r.fecha.isoformat(),
                "hora": r.hora.strftime("%H:%M"),
                "servicio": r.servicio,
                "estado": r.estado,
            }
            for r in reservas
        ],
        "pedidos": [
            {
                "fecha": p.fecha.strftime("%Y-%m-%d %H:%M") if p.fecha else None,
                "total": p.total,
                "estado": p.estado,
                "productos": [
                    {"nombre": pp.producto.nombre, "cantidad": pp.cantidad, "precio": pp.precio}
                    for pp in p.productos.all()
                ],
            }
            for p in pedidos
        ],
        "mensajes_de_contacto": [
            {"asunto": m.asunto, "tipo": m.tipo, "fecha": m.fecha.strftime("%Y-%m-%d %H:%M") if m.fecha else None}
            for m in mensajes
        ],
    }






def ayuda(request):
    contexto = contexto_carrito(request)
    contexto["tipos_mensaje"] = TIPOS_MENSAJE  # Opciones del dropdown de "tipo de mensaje"

    # Autocompletado: si la persona está logueada, sus datos se rellenan solos.
    logueado = request.session.get("logueado")
    if logueado and logueado.get("id"):
        usuario = Usuario.objects.only("nombre", "email").filter(pk=logueado["id"]).first()
        if usuario:
            contexto["prefill_nombre"] = usuario.nombre
            contexto["prefill_email"] = usuario.email

    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        email = request.POST.get("email", "").strip().lower()
        tipo = request.POST.get("tipo", "").strip()
        mensaje = request.POST.get("mensaje", "").strip()
        # Compatibilidad: si llega un "asunto" libre (versión antigua del formulario)
        # se usa como respaldo y se asocia al tipo "otro".
        asunto_libre = request.POST.get("asunto", "").strip()

        if tipo and tipo not in TIPOS_MENSAJE_DICCIONARIO:
            contexto["error"] = "Elige un tipo de mensaje de la lista."
            return render(request, "publicos/ayuda.html", contexto)
        if not tipo and not asunto_libre:
            contexto["error"] = "Elige un tipo de mensaje para poder enviar tu consulta."
            return render(request, "publicos/ayuda.html", contexto)

        asunto = TIPOS_MENSAJE_DICCIONARIO.get(tipo) or asunto_libre
        tipo_guardado = tipo or "otro"

        try:
            validate_email(email)
        except ValidationError:
            contexto["error"] = "Escribe un correo válido."
            return render(request, "publicos/ayuda.html", contexto)
        if len(nombre) > 100 or len(asunto) > 150:
            contexto["error"] = "El nombre o el asunto superan el límite permitido."
            return render(request, "publicos/ayuda.html", contexto)
        if nombre and email and mensaje:
            MensajeContacto.objects.create(nombre=nombre, email=email, asunto=asunto, tipo=tipo_guardado, mensaje=mensaje)
            admins = list(Usuario.objects.filter(rol="Admin", activo=True).only("id"))  # Una sola consulta
            if admins:
                Notificacion.objects.bulk_create([  # Una sola inserción para todos los admins
                    Notificacion(usuario=admin, mensaje=f"Nuevo mensaje de contacto: {asunto}.")
                    for admin in admins
                ])
            asunto_correo = asunto.replace("\r", " ").replace("\n", " ")
            enviar_correo_destino(
                settings.CONTACT_EMAIL,
                f"Nuevo mensaje de contacto: {asunto_correo}",
                f"Recibiste un nuevo mensaje desde el formulario de TecnoCorte.\n\nNombre: {nombre}\nCorreo del cliente: {email}\nTipo de mensaje: {asunto}\n\nMensaje:\n{mensaje}",
                request=request,
            )
            contexto["exito"] = "Tu mensaje fue enviado. Te responderemos pronto."
        else:
            contexto["error"] = "Completa todos los campos para enviar tu mensaje."
    return render(request, "publicos/ayuda.html", contexto)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CARRITO DE COMPRAS (funciona sin estar registrado)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•






# COMPRA


# ═══════════════════════════════════════════════════════════════════════════
# USUARIO/CLIENTE
# ═══════════════════════════════════════════════════════════════════════════























# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PELUQUERO
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•








# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PELUQUERÃA DEL BARBERO
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _peluqueria_del_barbero(usuario_id):
    """Devuelve la peluquería del barbero.

    La peluquería la crea o asigna siempre el Admin (el barbero ya no puede
    crear la suya), así que se respeta primero al dueño y luego la peluquería
    asignada en el perfil del barbero.
    """
    peluqueria = Peluqueria.objects.filter(dueno_id=usuario_id).first()
    if peluqueria:
        return peluqueria
    usuario = Usuario.objects.select_related("peluqueria").filter(id=usuario_id).first()
    if usuario and usuario.peluqueria_id:
        return usuario.peluqueria
    primera_reserva = Reserva.objects.filter(peluquero_id=usuario_id, peluqueria__isnull=False).order_by("fecha").first()
    if primera_reserva and primera_reserva.peluqueria:
        primera_reserva.peluqueria.dueno_id = usuario_id
        primera_reserva.peluqueria.save()
        return primera_reserva.peluqueria
    return None


# Aviso para el barbero al que el Admin todavía no le ha asignado una peluquería
SIN_PELUQUERIA = "Tu barbería aún no está asignada. Pídele al administrador que te cree una o te asigne a una existente."









# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ADMIN
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•




def _respuesta_reporte_excel(titulo, subtitulo, encabezados, filas, nombre_archivo):
    """Genera un HTML con estilos que Excel abre como hoja formateada (.xls)."""
    encabezados_html = "".join(f"<th>{escape(str(encabezado))}</th>" for encabezado in encabezados)
    filas_html = "".join(
        "<tr>" + "".join(f"<td>{escape(str(valor))}</td>" for valor in fila) + "</tr>"
        for fila in filas
    ) or f'<tr><td colspan="{len(encabezados)}" class="empty">No hay registros para mostrar</td></tr>'
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
    body{{font-family:Arial,sans-serif;color:#27231b;background:#fff;padding:24px}}
    .report{{max-width:1400px;margin:auto}}
    h1{{margin:0;color:#6f520d;font-size:24px}} .subtitle{{color:#777;margin:6px 0 20px;font-size:13px}}
    .meta{{background:#f6edcf;border:1px solid #d6ad42;padding:10px 14px;margin-bottom:18px;font-size:12px}}
    table{{border-collapse:collapse;width:100%;font-size:12px}} th{{background:#6f520d;color:#fff;padding:11px 9px;text-align:left;white-space:nowrap}}
    td{{border:1px solid #ded8c9;padding:9px;background:#fff}} tr:nth-child(even) td{{background:#faf7ef}}
    .empty{{text-align:center;color:#777;padding:22px}} .total{{font-weight:bold;color:#6f520d}}
    </style></head><body><div class="report"><h1>{escape(titulo)}</h1><p class="subtitle">{escape(subtitulo)}</p>
    <div class="meta">Generado por TecnoCorte Â· Registros: <strong>{len(filas)}</strong></div>
    <table><thead><tr>{encabezados_html}</tr></thead><tbody>{filas_html}</tbody></table></div></body></html>"""
    respuesta = HttpResponse("\ufeff" + html, content_type="application/vnd.ms-excel; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    return respuesta

























# Motivo que el Admin debe escribir al eliminar una foto (obligatorio)
def _motivo_eliminacion(request):
    """Devuelve el motivo escrito al borrar una foto, o None si está vacío.

    Es obligatorio para que el autor de la foto reciba una explicación.
    """
    return request.POST.get("motivo", "").strip() or None


# Avisa por correo al autor de una foto que el Admin la eliminó y por qué
def avisar_foto_eliminada(usuario, descripcion_foto, motivo, request=None):
    """Envía al autor de la foto el motivo por el que el Admin la eliminó."""
    if not usuario:
        return
    cuerpo = (
        f"Un administrador de TecnoCorte eliminó {descripcion_foto}.\n\n"
        f"Motivo: {motivo}\n\n"
        "Si crees que fue un error, responde a este correo o contacta con soporte."
    )
    enviar_correo(usuario, "Una de tus fotos fue eliminada", cuerpo, request=request)










def notificar_producto_agotado(producto):
    mensaje = f"Stock agotado: {producto.nombre}."
    admins = list(Usuario.objects.filter(rol="Admin", activo=True).only("id"))  # Una sola consulta
    if admins:
        Notificacion.objects.bulk_create(  # Una sola inserción para todos los admins
            [Notificacion(usuario=admin, mensaje=mensaje, fecha=timezone.now()) for admin in admins]
        )


def datos_producto(request, producto=None):
    stock_anterior = producto.stock if producto.pk else None
    nombre = request.POST.get("nombre", "").strip()
    if not nombre or len(nombre) > 100:
        return "El nombre del producto es obligatorio y no puede superar 100 caracteres."
    try:
        precio = int(request.POST.get("precio", ""))
        stock = int(request.POST.get("stock", ""))
    except (TypeError, ValueError):
        return "El precio y el stock deben ser números enteros."
    if precio < 0 or stock < 0:
        return "El precio y el stock no pueden ser negativos."
    categoria = request.POST.get("categoria", "Herramientas")
    if categoria not in dict(Producto.CATEGORIAS):
        return "La categoría seleccionada no es válida."
    producto.nombre = nombre
    producto.descripcion = request.POST.get("descripcion", "")
    producto.precio = precio
    producto.categoria = categoria
    producto.stock = stock
    producto.disponible = request.POST.get("disponible") == "on" and producto.stock > 0
    # El Admin puede quitar la foto actual o reemplazarla por una nueva.
    if request.POST.get("quitar_imagen") and producto.imagen:
        _borrar_archivo(producto.imagen)
        producto.imagen = ""
    imagen = request.FILES.get("imagen")
    error_imagen = validar_imagen(imagen)
    if error_imagen:
        return error_imagen
    if imagen:
        if producto.imagen:
            _borrar_archivo(producto.imagen)
        producto.imagen = imagen
    producto.save()
    if stock_anterior and stock_anterior > 0 and producto.stock == 0:
        notificar_producto_agotado(producto)
    return ""



















# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# GESTIÃ“N DE USUARIOS - SOLO ADMIN
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•









# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CONFIGURACIÃ“N GENERAL DEL SITIO - SOLO ADMIN
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


# Implementaciones trasladadas por dominio; se importan al final para conservar compatibilidad.
# La fachada activa (`sena.views`) importa la autenticación después de cargar
# este módulo; importar aquí de vuelta provocaría un ciclo al verificar correo.
from .publicas import inicio, como_funciona, sobre_nosotros, politicas, health_check, ayuda
from .carrito import carrito, _cliente_o_invitado, agregar_carrito, actualizar_carrito, eliminar_carrito, finalizar_pedido, pedido_exitoso
from .clientes import usuario_dashboard, usuario_tienda, usuario_producto_detalle, usuario_servicios, usuario_peluquerias, usuario_peluqueria_detalle, usuario_perfil, usuario_configuracion, usuario_notificaciones, usuario_marcar_notificaciones_leidas
from .reservas import usuario_reservar_cita, usuario_pre_confirmar, usuario_confirmar_reserva, usuario_cancelar_reserva, usuario_editar_reserva, usuario_confirmar_cita_peluquero, usuario_calificar
from .barberos import peluquero_dashboard, peluquero_configuracion, peluquero_cambiar_estado, peluquero_perfil, peluquero_crear_cita, peluquero_notificaciones, peluquero_editar_peluqueria, peluquero_galeria, peluquero_agregar_imagen, peluquero_eliminar_imagen
from .administrador import admin_editar_inicio, admin_dashboard, admin_exportar_reservas, admin_exportar_pedidos, admin_peluqueros, admin_crear_peluquero, admin_editar_peluquero, admin_eliminar_peluquero, admin_reservas, admin_pedidos, admin_actualizar_pedido, admin_crear_reserva, admin_editar_reserva, admin_eliminar_reserva, admin_cancelar_reserva, admin_horarios, admin_eliminar_bloqueo, admin_peluquerias, admin_crear_peluqueria, admin_editar_peluqueria, admin_eliminar_peluqueria, admin_quitar_foto_peluqueria, admin_galeria, admin_eliminar_imagen_galeria, admin_productos, admin_crear_producto, admin_editar_producto, admin_eliminar_producto, admin_quitar_imagen_producto, admin_mensajes, admin_solicitudes_servicios, admin_notificaciones, admin_perfil, admin_ingresos, admin_acciones, admin_usuarios, admin_crear_usuario, admin_editar_usuario, admin_eliminar_usuario, admin_suspender_usuario, admin_quitar_foto_usuario, admin_configuracion
