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
from ..models import Usuario, RegistroPendiente, Peluqueria, ImagenPeluqueria, Producto, Reserva, Pedido, PedidoProducto, RegistroIngreso, Notificacion, HorarioTrabajo, BloqueoHorario, MensajeContacto, Calificacion, Configuracion, Servicio, SolicitudServicio, TIPOS_MENSAJE, TIPOS_MENSAJE_DICCIONARIO  # Todos los modelos
from ..utilidades import autorizacion, validar_password, validar_telefono, validar_imagen, registrar_accion, transicion_valida, TRANSICIONES_RESERVA, TRANSICIONES_PEDIDO  # Seguridad, auditoría, estados y validación
from ..context_processors import carrito_visible, guardar_carrito_activo, cargar_carrito_usuario  # Funciones del carrito por sesión
from ..services.correos import enviar_correo, enviar_correo_destino, enviar_correo_cita
from ..services.autenticacion import enviar_codigo_verificacion, url_publica
from ..services.pedidos import actualizar_pedido
from ..services.catalogo import SERVICIOS, DURACIONES_SERVICIO, catalogo_servicios, servicio_valido, minutos_servicio

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

# Cada cliente puede publicar como máximo dos reseñas en el inicio.
RESENAS_POR_PERSONA = 2

# Única cuenta autorizada para asignar o cambiar roles. El resto de
# administradores puede gestionar datos, imágenes y estados, pero no escalar
# cuentas a Admin ni convertir usuarios en Barberos.
ADMIN_PRINCIPAL_EMAIL = "tecnocorte083@gmail.com"


def puede_gestionar_roles(request):
    """Comprueba el permiso real desde la BD, no desde datos manipulables de sesión."""
    usuario_id = (request.session.get("logueado") or {}).get("id")
    return bool(
        usuario_id
        and Usuario.objects.filter(
            id=usuario_id, activo=True, rol="Admin", email__iexact=ADMIN_PRINCIPAL_EMAIL
        ).exists()
    )


def resenas_restantes(cliente_id):
    """Reseñas que le quedan por publicar a un cliente."""
    usadas = Calificacion.objects.filter(cliente_id=cliente_id).count()
    return max(RESENAS_POR_PERSONA - usadas, 0)

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
def cita_disponible(fecha_texto, hora_texto, peluqueria_id=None, servicio=None):
    """Revisa horarios de trabajo, bloqueos y fecha/hora válida antes de crear una cita."""
    try:
        fecha = datetime.strptime(fecha_texto, "%Y-%m-%d").date()  # Convierte texto a fecha
        hora = datetime.strptime(hora_texto, "%H:%M").time()  # Convierte texto a hora
    except (TypeError, ValueError):
        return False, "La fecha o la hora no son válidas."  # Formato inválido
    if fecha < timezone.localdate():
        return False, "No puedes reservar una fecha pasada."  # No se puede reservar en el pasado
    ahora = timezone.localtime()  # Hora actual del servidor
    if fecha == ahora.date() and hora <= ahora.time().replace(second=0, microsecond=0):
        return False, "No puedes reservar una hora que ya pasó. Elige una hora posterior a la actual."  # No reservar hora pasada hoy

    horarios = HorarioTrabajo.objects.filter(dia_semana=fecha.weekday())  # Busca horarios para ese día de la semana
    if peluqueria_id:
        horarios = horarios.filter(peluqueria_id=peluqueria_id)  # Filtra por peluquería
    horario = horarios.first()  # Toma el primer horario encontrado
    if horario is None:
        return False, "Esta barbería todavía no tiene horarios configurados."  # Sin horarios configurados
    if not horario.activo:
        return False, "Ese día no se trabaja. Elige otra fecha."  # Día inactivo
    duracion = minutos_servicio(servicio)  # Obtiene la duración del servicio
    hora_fin_servicio = (datetime.combine(fecha, hora) + timedelta(minutes=duracion)).time()  # Calcula hora de fin
    if hora < horario.hora_inicio or hora_fin_servicio > horario.hora_fin:
        return False, "La hora elegida está por fuera del horario de atención."  # Fuera del horario
    bloqueos = BloqueoHorario.objects.filter(fecha=fecha)  # Busca bloqueos para esa fecha
    if peluqueria_id:
        bloqueos = bloqueos.filter(peluqueria_id=peluqueria_id)  # Filtra por peluquería
    if bloqueos.filter(hora__isnull=True).exists():
        return False, "Ese día está bloqueado para citas."  # Día completo bloqueado
    inicio_bloqueo = datetime.combine(fecha, hora)  # Inicio de la cita
    fin_bloqueo = inicio_bloqueo + timedelta(minutes=duracion)  # Fin de la cita
    for bloqueo in bloqueos.exclude(hora__isnull=True):  # Revisa bloqueos por hora
        bloqueo_inicio = datetime.combine(fecha, bloqueo.hora)  # Inicio del bloqueo
        if inicio_bloqueo < bloqueo_inicio + timedelta(minutes=30) and fin_bloqueo > bloqueo_inicio:
            return False, "Ese horario está bloqueado. Elige otra hora."  # Choca con un bloqueo
    return True, ""  # Todo OK, la cita está disponible


# Avisa a todos los Admin activos de un evento (una sola inserción)
def notificar_admins(mensaje):
    admins = list(Usuario.objects.filter(rol="Admin", activo=True).only("id"))
    if admins:
        Notificacion.objects.bulk_create(
            [Notificacion(usuario=admin, mensaje=mensaje, fecha=timezone.now()) for admin in admins]
        )


def barberos_disponibles():
    """Barberos activos y asignados a una barbería, aptos para reservar."""
    return Usuario.objects.filter(
        rol="Barbero", activo=True, peluqueria__isnull=False
    ).select_related("peluqueria")


# Formatea la fecha y hora de una reserva para mostrar en notificaciones y correos
def formato_cita(reserva):
    """Mantiene una fecha y hora legibles y consistentes en todos los avisos."""
    fecha = reserva.fecha if hasattr(reserva.fecha, "strftime") else datetime.strptime(str(reserva.fecha), "%Y-%m-%d").date()  # Asegura que sea objeto date
    hora = reserva.hora if hasattr(reserva.hora, "strftime") else datetime.strptime(str(reserva.hora), "%H:%M").time()  # Asegura que sea objeto time
    return f"{fecha.strftime('%d/%m/%Y')} a las {hora.strftime('%H:%M')}"  # Formato: "01/01/2026 a las 10:00"


# Salt para generar tokens de recuperación de contraseña (evita que se adivinen)
RESET_SALT = "tecnocorte-password-reset"


# Genera un token firmado para recuperar la contraseña (válido 1 hora)
def token_recuperacion(usuario):
    version = salted_hmac(RESET_SALT, usuario.password).hexdigest()  # Versión basada en la contraseña actual
    return signing.dumps({"id": usuario.id, "version": version}, salt=RESET_SALT, compress=True)  # Token firmado y comprimido


# Valida un token de recuperación y devuelve el usuario si es válido
def usuario_desde_token(token):
    try:
        datos = signing.loads(token, salt=RESET_SALT, max_age=3600)  # Descifra el token (máx 1 hora)
    except (signing.BadSignature, signing.SignatureExpired, TypeError, ValueError):
        return None  # Token inválido o expirado
    usuario = Usuario.objects.filter(id=datos.get("id"), activo=True).first()  # Busca el usuario
    if not usuario:
        return None  # Usuario no existe o está inactivo
    version_actual = salted_hmac(RESET_SALT, usuario.password).hexdigest()  # Versión actual
    return usuario if hmac.compare_digest(datos.get("version", ""), version_actual) else None  # Compara versiones de forma segura


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
def barbero_esta_disponible(barbero_id, fecha_texto, hora_texto, servicio, reserva_actual=None):
    """Evita cruces de citas y reserva todo el tiempo que dura cada servicio."""
    try:
        inicio = datetime.combine(datetime.strptime(fecha_texto, "%Y-%m-%d").date(), datetime.strptime(hora_texto, "%H:%M").time())  # Inicio propuesto
    except (TypeError, ValueError):
        return False, "La fecha o la hora no son válidas."  # Formato inválido
    fin = inicio + timedelta(minutes=minutos_servicio(servicio))  # Fin propuesto según duración del servicio
    citas = Reserva.objects.filter(peluquero_id=barbero_id, fecha=fecha_texto).exclude(estado="Cancelada")  # Todas las citas del barbero ese día
    if reserva_actual:
        citas = citas.exclude(id=reserva_actual.id)  # Excluye la reserva actual si se está editando
    for cita in citas:
        inicio_existente = datetime.combine(cita.fecha, cita.hora)  # Inicio de la cita existente
        fin_existente = inicio_existente + timedelta(minutes=minutos_servicio(cita.servicio))  # Fin de la cita existente
        if inicio < fin_existente and fin > inicio_existente:
            return False, "El barbero ya tiene una cita que ocupa ese horario."  # Hay cruce de horarios
    return True, ""  # No hay conflicto, el barbero está disponible

# INICIO - Sin login
def contenido_inicio():
    """Servicios, productos y reseñas que se muestran en la página principal.

    El Admin elige qué dos servicios y qué dos productos se destacan. Si deja
    alguno sin elegir, la portada usa los de siempre (los primeros servicios del
    catálogo y la pomada con el aceite) para que nunca quede con huecos.
    """
    config = Configuracion.cargar()

    # ── Servicios destacados ──
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

    # ── Productos destacados ──
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

    # ── Reseñas reales: solo se publican si el Admin lo permite ──
    # Se traen todas: el inicio muestra las primeras y "Ver más" despliega el resto.
    resenas = []
    if config.mostrar_calificaciones:
        resenas = list(
            Calificacion.objects.select_related("cliente", "barbero").all()
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
    # Reseñas desde la portada: un cliente con sesión puede dejar hasta dos.
    sesion = request.session.get("logueado")
    if sesion and sesion.get("rol") == "Cliente":
        restantes = resenas_restantes(sesion["id"])
        contexto["resenas_restantes"] = restantes
        contexto["resenas_por_persona"] = RESENAS_POR_PERSONA
        contexto["puede_resenar"] = restantes > 0
    return render(request, "publicos/index.html", contexto)


@autorizacion(["Cliente"])
def usuario_dejar_resena(request):
    """Publica una reseña escrita directamente desde la portada (máximo dos por persona)."""
    destino = reverse("sena:inicio") + "#resenas"
    if request.method != "POST":
        return redirect(destino)
    cliente_id = request.session["logueado"]["id"]
    if resenas_restantes(cliente_id) <= 0:
        messages.error(request, f"Ya publicaste tus {RESENAS_POR_PERSONA} reseñas permitidas.")
        return redirect(destino)
    try:
        puntuacion = int(request.POST.get("puntuacion", 0))
    except (TypeError, ValueError):
        puntuacion = 0
    if puntuacion < 1 or puntuacion > 5:
        messages.error(request, "Elige de 1 a 5 estrellas para publicar tu reseña.")
        return redirect(destino)
    Calificacion.objects.create(
        cliente_id=cliente_id,
        puntuacion=puntuacion,
        comentario=request.POST.get("comentario", "").strip(),
    )
    messages.success(request, "¡Gracias por tu reseña!")
    return redirect(destino)


@autorizacion(["Admin"])
def admin_editar_inicio(request):
    """El Admin elige qué servicios y productos ya existentes se destacan en el inicio."""
    config = Configuracion.cargar()
    catalogo = catalogo_servicios()
    productos = Producto.objects.filter(disponible=True).order_by("categoria", "nombre")

    if request.method == "POST":
        nombres_validos = {s["nombre"] for s in catalogo}
        ids_validos = {p.id for p in productos}

        def servicio_elegido(campo):
            nombre = request.POST.get(campo, "").strip()
            return nombre if nombre in nombres_validos else ""

        def producto_elegido(campo):
            pid = _id_entero(request.POST.get(campo))
            return Producto.objects.filter(id=pid).first() if pid in ids_validos else None

        config.servicio_destacado_1 = servicio_elegido("servicio_destacado_1")
        config.servicio_destacado_2 = servicio_elegido("servicio_destacado_2")
        config.producto_destacado_1 = producto_elegido("producto_destacado_1")
        config.producto_destacado_2 = producto_elegido("producto_destacado_2")
        config.save()  # save() limpia la caché, así que el cambio se ve al instante
        messages.success(request, "El inicio se actualizó correctamente.")
        return redirect("sena:admin_editar_inicio")

    return render(request, "administrador/admin_editar_inicio.html", {
        "config": config,
        "servicios": catalogo,
        "productos": productos,
        "productos_por_defecto": ", ".join(PRODUCTOS_DESTACADOS_POR_DEFECTO),
        "seleccion_servicios": [config.servicio_destacado_1, config.servicio_destacado_2],
        "seleccion_productos": [
            config.producto_destacado_1.id if config.producto_destacado_1 else None,
            config.producto_destacado_2.id if config.producto_destacado_2 else None,
        ],
    })


# LOGIN
def login(request):
    if request.method == "POST":
        email = request.POST.get("user")
        password = request.POST.get("password")
        proximo = request.POST.get("next", "")

        # Bloqueo anti fuerza bruta: 5 intentos fallidos bloquean 5 minutos (por correo + IP)
        ip = request.META.get("REMOTE_ADDR", "")
        clave_base = f"{(email or '').strip().lower()}_{ip}"
        clave_intentos = f"login_intentos_{clave_base}"
        clave_bloqueo = f"login_bloqueo_{clave_base}"
        if cache.get(clave_bloqueo):
            return render(request, "publicos/login.html", {"error": "Demasiados intentos fallidos. Espera 5 minutos e inténtalo de nuevo.", "proximo": proximo})

        try:
            usuario = Usuario.objects.get(email=email)
            if not check_password(password, usuario.password):
                raise Usuario.DoesNotExist
            if not usuario.activo:
                return render(request, "publicos/login.html", {"error": "Tu cuenta ha sido suspendida. Contacta al administrador para más información.", "proximo": proximo})
            # Login correcto: se limpia el contador de intentos
            cache.delete(clave_intentos)

            guardar_carrito_activo(request)
            # Rota la clave de sesión para evitar fijación de sesión al iniciar sesión.
            request.session.cycle_key()
            request.session["logueado"] = {
                "id": usuario.id,
                "nombre": usuario.nombre,
                "rol": usuario.rol,
                "sesion_version": usuario.sesion_version,
            }
            cargar_carrito_usuario(request, usuario.id)

            registrar_ingreso(request, usuario)
            registrar_accion(request, "inicio_sesion", "Usuario", usuario.id)
            messages.success(request, f"Bienvenido de nuevo, {usuario.nombre}.")

            # Si hay un "next" (página a la que quería ir), redirigir allá
            if proximo and url_has_allowed_host_and_scheme(proximo, {request.get_host()}, require_https=request.is_secure()):
                return redirect(proximo)

            if proximo == "carrito":
                return redirect("sena:carrito")

            if usuario.rol == "Admin":
                return redirect("sena:admin_dashboard")
            elif usuario.rol == "Barbero":
                return redirect("sena:peluquero_dashboard")
            else:
                return redirect("sena:inicio")
        except Usuario.DoesNotExist:
            # Cuenta el intento fallido; al llegar a 5 bloquea durante 5 minutos
            intentos = cache.get(clave_intentos, 0) + 1
            if intentos >= 5:
                cache.set(clave_bloqueo, True, 300)
                cache.delete(clave_intentos)
                return render(request, "publicos/login.html", {"error": "Demasiados intentos fallidos. Espera 5 minutos e inténtalo de nuevo.", "proximo": proximo})
            cache.set(clave_intentos, intentos, 300)
            return render(request, "publicos/login.html", {"error": f"Credenciales incorrectas. Te quedan {5 - intentos} intentos.", "proximo": proximo})

    # Un Admin con sesión iniciada no vuelve a ver el formulario: aterriza en su panel.
    logueado = request.session.get("logueado")
    if logueado and logueado.get("rol") == "Admin":
        return redirect("sena:admin_dashboard")
    return render(request, "publicos/login.html", {"proximo": request.GET.get("next", "")})


def solicitar_recuperacion(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if not email:
            return render(request, "publicos/recuperar_password.html", {"error": "Escribe el correo de tu cuenta."})
        try:
            validate_email(email)
        except ValidationError:
            return render(request, "publicos/recuperar_password.html", {"error": "Escribe un correo válido."})

        usuario = Usuario.objects.filter(email__iexact=email, activo=True).first()
        if usuario:
            token = token_recuperacion(usuario)
            enlace = request.build_absolute_uri(reverse("sena:restablecer_password", args=[token]))
            enviar_correo(
                usuario,
                "Recupera tu contraseña de TecnoCorte",
                f"Hola {usuario.nombre},\n\nRecibimos una solicitud para cambiar la contraseña de tu cuenta. El enlace será válido durante una hora.\n\nSi no solicitaste este cambio, puedes ignorar este mensaje.",
                request=request,
                enlace=enlace,
                texto_enlace="Cambiar mi contraseña",
            )
        return render(request, "publicos/recuperar_password.html", {"enviado": True})
    return render(request, "publicos/recuperar_password.html")


def restablecer_password(request, token):
    usuario = usuario_desde_token(token)
    if not usuario:
        return render(request, "publicos/restablecer_password.html", {"valido": False})
    if request.method == "POST":
        password = request.POST.get("password", "")
        confirmacion = request.POST.get("password_confirm", "")
        if password != confirmacion:
            return render(request, "publicos/restablecer_password.html", {"valido": True, "error": "Las contraseñas no coinciden."})
        error_password = validar_password(password)
        if error_password:
            return render(request, "publicos/restablecer_password.html", {"valido": True, "error": error_password})
        usuario.password = make_password(password)
        usuario.save(update_fields=["password"])
        messages.success(request, "Contraseña actualizada. Ya puedes iniciar sesión.")
        return redirect("sena:login")
    return render(request, "publicos/restablecer_password.html", {"valido": True})

# LOGOUT
def logout(request):
    guardar_carrito_activo(request)
    if request.session.get("logueado"):
        del request.session["logueado"]
    request.session.pop("carrito_usuario_id", None)
    request.session["carrito"] = request.session.get("carritos_usuario", {}).get("anonimo", {})
    return redirect("sena:inicio")

# REGISTRO DE CLIENTES
def registro(request):
    # La política de privacidad puede desactivar el registro de nuevos clientes.
    if not Configuracion.cargar().registro_abierto:
        return render(request, "publicos/registro.html", {
            "error": "El registro de nuevas cuentas está desactivado por el administrador.",
            "registro_cerrado": True,
        })
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        email = request.POST.get("email", "").strip().lower()
        telefono = request.POST.get("telefono", "").strip()
        password = request.POST.get("password", "")
        proximo = request.POST.get("next", "")

        if not nombre or not apellido or not email or not password:
            return render(request, "publicos/registro.html", {"error": "Completa todos los campos obligatorios."})
        if len(nombre) > 100 or len(apellido) > 100:
            return render(request, "publicos/registro.html", {"error": "El nombre y el apellido no pueden superar 100 caracteres."})
        error_telefono = validar_telefono(telefono)
        if error_telefono:
            return render(request, "publicos/registro.html", {"error": error_telefono})

        # El correo debe tener un formato válido
        try:
            validate_email(email)
        except ValidationError:
            return render(request, "publicos/registro.html", {"error": "Ese correo no tiene un formato válido."})

        # La contraseña debe cumplir las reglas de seguridad
        error_password = validar_password(password)
        if error_password:
            return render(request, "publicos/registro.html", {"error": error_password})

        if Usuario.objects.filter(email__iexact=email).exists():
            return render(request, "publicos/registro.html", {"error": "Ya existe una cuenta con ese correo."})

        try:
            pendiente, _ = RegistroPendiente.objects.update_or_create(
                email=email,
                defaults={
                    "nombre": nombre,
                    "apellido": apellido,
                    "telefono": telefono,
                    "password": make_password(password),
                    "codigo_hash": hashlib.sha256(secrets.token_bytes(16)).hexdigest(),
                    "codigo_expira": timezone.now(),
                    "token_hash": hashlib.sha256(secrets.token_bytes(16)).hexdigest(),
                    "token_expira": timezone.now(),
                    "ultimo_envio": None,
                },
            )
        except IntegrityError:
            return render(request, "publicos/registro.html", {"error": "Ya existe una cuenta con ese correo."})
        ruta = reverse("sena:verificar_correo")
        enviado, token = enviar_codigo_verificacion(
            request, pendiente, lambda value: url_publica(request, f"{ruta}?token={value}")
        )
        request.session["registro_pendiente_token"] = token
        request.session["registro_pendiente_next"] = proximo
        return render(request, "publicos/verificar_correo.html", {
            "pendiente": pendiente, "token": token, "proximo": proximo, "enviado": enviado,
        })

    return render(request, "publicos/registro.html", {"proximo": request.GET.get("next", "")})
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


# ═══════════════════════════════════════════════════════════════════════════
# ZONA DE CONFIGURACIÓN (cliente y barbero)
# ═══════════════════════════════════════════════════════════════════════════

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


@autorizacion(["Cliente"])
def usuario_configuracion(request):
    """Zona de configuración del cliente: Perfil, Seguridad, Notificaciones y Privacidad."""
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    pestana = _pestanas_config(request, PESTANAS_CONFIG_USUARIO)

    if request.method == "POST":
        accion = request.POST.get("accion", "")

        if accion == "perfil":
            telefono = request.POST.get("telefono", usuario.telefono).strip()
            error_telefono = validar_telefono(telefono)
            if error_telefono:
                messages.error(request, error_telefono)
                return redirect(f"{reverse('sena:usuario_configuracion')}?seccion=perfil")
            foto = request.FILES.get("foto")
            error_imagen = validar_imagen(foto)
            if error_imagen:
                messages.error(request, error_imagen)
                return redirect(f"{reverse('sena:usuario_configuracion')}?seccion=perfil")
            usuario.nombre = request.POST.get("nombre", usuario.nombre).strip() or usuario.nombre
            usuario.apellido = request.POST.get("apellido", usuario.apellido).strip() or usuario.apellido
            usuario.telefono = telefono
            if foto:
                usuario.foto = foto
            usuario.save()
            # Se reasigna el diccionario completo: Django no detecta cambios anidados.
            request.session["logueado"] = {**request.session["logueado"], "nombre": usuario.nombre}
            enviar_correo(
                usuario,
                "Tu perfil fue actualizado",
                f"Hola {usuario.nombre},\n\nTus datos de perfil fueron actualizados correctamente en TecnoCorte.",
                request=request,
                enlace=request.build_absolute_uri(reverse("sena:usuario_configuracion")),
                texto_enlace="Revisar mi perfil",
            )
            messages.success(request, "Perfil actualizado correctamente.")
            return redirect(f"{reverse('sena:usuario_configuracion')}?seccion=perfil")

        if accion == "notificaciones":
            _datos_notificacion(request, usuario)
            messages.success(request, "Preferencias de notificaciones guardadas.")
            return redirect(f"{reverse('sena:usuario_configuracion')}?seccion=notificaciones")

        if accion == "descarga":
            respuesta = JsonResponse(
                _datos_descargables(usuario),
                json_dumps_params={"ensure_ascii": False, "indent": 2},
            )
            respuesta["Content-Disposition"] = 'attachment; filename="mis_datos_tecnocorte.json"'
            return respuesta

        if accion == "privacidad":
            messages.success(request, "Preferencias de privacidad actualizadas.")
            return redirect(f"{reverse('sena:usuario_configuracion')}?seccion=privacidad")

    contexto = contexto_carrito(request)
    contexto.update({
        "usuario": usuario,
        "pestana": pestana,
        "pestanas": PESTANAS_CONFIG_USUARIO,
        "ingresos": RegistroIngreso.objects.filter(usuario=usuario).order_by("-fecha")[:5],
    })
    return render(request, "usuarios/usuario_configuracion.html", contexto)


@autorizacion(["Barbero"])
def peluquero_configuracion(request):
    """Configuración del barbero: Portafolio, Agenda, Servicios y Notificaciones."""
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    pestana = _pestanas_config(request, PESTANAS_CONFIG_PELUQUERO)

    if request.method == "POST":
        accion = request.POST.get("accion", "")

        if accion == "portafolio":
            telefono = request.POST.get("telefono", usuario.telefono).strip()
            error_telefono = validar_telefono(telefono)
            if error_telefono:
                messages.error(request, error_telefono)
                return redirect(f"{reverse('sena:peluquero_configuracion')}?seccion=portafolio")
            foto = request.FILES.get("foto")
            error_imagen = validar_imagen(foto)
            if error_imagen:
                messages.error(request, error_imagen)
                return redirect(f"{reverse('sena:peluquero_configuracion')}?seccion=portafolio")
            usuario.nombre = request.POST.get("nombre", usuario.nombre).strip() or usuario.nombre
            usuario.apellido = request.POST.get("apellido", usuario.apellido).strip() or usuario.apellido
            usuario.telefono = telefono
            if foto:
                usuario.foto = foto
            usuario.save()
            # Se reasigna el diccionario completo: Django no detecta cambios anidados.
            request.session["logueado"] = {**request.session["logueado"], "nombre": usuario.nombre}
            enviar_correo(
                usuario,
                "Tu perfil de barbero fue actualizado",
                f"Hola {usuario.nombre},\n\nTus datos de perfil fueron actualizados correctamente en TecnoCorte.",
                request=request,
                enlace=request.build_absolute_uri(reverse("sena:peluquero_configuracion")),
                texto_enlace="Revisar mi configuración",
            )
            messages.success(request, "Portafolio actualizado correctamente.")
            return redirect(f"{reverse('sena:peluquero_configuracion')}?seccion=portafolio")

        if accion == "notificaciones":
            _datos_notificacion(request, usuario)
            messages.success(request, "Preferencias de notificaciones guardadas.")
            return redirect(f"{reverse('sena:peluquero_configuracion')}?seccion=notificaciones")

        if accion == "solicitar_servicio":
            destino = f"{reverse('sena:peluquero_configuracion')}?seccion=servicios"
            nombre = request.POST.get("nombre", "").strip()
            if not nombre or len(nombre) > 100:
                messages.error(request, "El nombre del servicio es obligatorio y no puede superar 100 caracteres.")
                return redirect(destino)
            if nombre in {item["nombre"] for item in SERVICIOS}:
                messages.info(request, f"«{nombre}» ya es un servicio del sistema; no hace falta pedirlo.")
                return redirect(destino)
            try:
                precio = int(str(request.POST.get("precio", "")).replace(".", "").replace(",", "").replace(" ", ""))
                minutos = int(request.POST.get("minutos", "30"))
            except (TypeError, ValueError):
                messages.error(request, "El precio y la duración deben ser números.")
                return redirect(destino)
            if precio < 0:
                messages.error(request, "El precio no puede ser negativo.")
                return redirect(destino)
            if minutos not in DURACIONES_SERVICIO:
                messages.error(request, "Elige una duración válida de la lista.")
                return redirect(destino)
            if Servicio.objects.filter(barbero=usuario, nombre__iexact=nombre).exists():
                messages.info(request, f"Ya ofreces el servicio «{nombre}».")
                return redirect(destino)
            if SolicitudServicio.objects.filter(barbero=usuario, estado="pendiente", nombre__iexact=nombre).exists():
                messages.info(request, f"Ya tienes una solicitud pendiente para «{nombre}».")
                return redirect(destino)
            descripcion = request.POST.get("descripcion", "").strip()[:300]
            SolicitudServicio.objects.create(
                barbero=usuario,
                nombre=nombre,
                descripcion=descripcion,
                duracion=f"{minutos} Minutos",
                minutos=minutos,
                precio=precio,
            )
            nombre_completo = f"{usuario.nombre} {usuario.apellido}".strip() or usuario.email
            notificar_admins(f"{nombre_completo} solicita crear el servicio «{nombre}» ({minutos} min, ${precio} COP).")
            cache.delete("contador_solicitudes_servicio_admin")
            messages.success(request, "Solicitud enviada. El administrador la revisará y te avisará.")
            return redirect(destino)

        if accion == "cancelar_solicitud":
            destino = f"{reverse('sena:peluquero_configuracion')}?seccion=servicios"
            solicitud_id = _id_entero(request.POST.get("solicitud_id"))
            canceladas, _ = SolicitudServicio.objects.filter(
                id=solicitud_id, barbero=usuario, estado="pendiente"
            ).delete()
            if canceladas:
                messages.info(request, "Solicitud cancelada.")
            else:
                messages.error(request, "No se pudo cancelar esa solicitud.")
            return redirect(destino)

    peluqueria = _peluqueria_del_barbero(usuario.id)
    contexto = {
        "usuario": usuario,
        "pestana": pestana,
        "pestanas": PESTANAS_CONFIG_PELUQUERO,
        "peluqueria": peluqueria,
        "servicios": SERVICIOS,
        "mis_servicios": Servicio.objects.filter(barbero=usuario).order_by("nombre"),
        "solicitudes": SolicitudServicio.objects.filter(barbero=usuario)[:20],
        "solicitudes_pendientes": SolicitudServicio.objects.filter(barbero=usuario, estado="pendiente").count(),
        "duraciones": DURACIONES_SERVICIO,
        "horarios": HorarioTrabajo.objects.filter(peluqueria=peluqueria).order_by("dia_semana") if peluqueria else [],
        "bloqueos": BloqueoHorario.objects.filter(peluqueria=peluqueria).order_by("-fecha", "hora")[:10] if peluqueria else [],
        "fotos": peluqueria.galeria.all().order_by("-fecha")[:12] if peluqueria else [],
        "ingresos": RegistroIngreso.objects.filter(usuario=usuario).order_by("-fecha")[:5],
    }
    return render(request, "peluqueros/peluquero_configuracion.html", contexto)

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

# ═══════════════════════════════════════════════════════════════════════════
# CARRITO DE COMPRAS (funciona sin estar registrado)
# ═══════════════════════════════════════════════════════════════════════════

def carrito(request):
    contexto = contexto_carrito(request)
    return render(request, "carrito/carrito.html", contexto)

def _cliente_o_invitado(request):
    """True si la sesión no está logueada o pertenece a un Cliente (los demás roles solo pueden ver la tienda/carrito)."""
    logueado = request.session.get("logueado")
    return not logueado or logueado.get("rol") == "Cliente"

def agregar_carrito(request, producto_id):
    es_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not _cliente_o_invitado(request):
        if es_ajax:
            return JsonResponse({"error": "Solo los clientes pueden agregar productos al carrito."}, status=403)
        request.session["mensaje_carrito"] = "Solo los clientes pueden agregar productos al carrito."
        return redirect("sena:carrito")
    if not carrito_visible(request):
        if request.session.get("logueado"):
            cargar_carrito_usuario(request, request.session["logueado"]["id"])
        else:
            request.session["carrito"] = {}
            request.session.pop("carrito_usuario_id", None)
    try:
        producto = Producto.objects.get(id=producto_id)
    except Producto.DoesNotExist:
        if es_ajax:
            return JsonResponse({"error": "El producto no está disponible."}, status=404)
        request.session["mensaje_tienda"] = "El producto no está disponible."
        return redirect("sena:usuario_tienda")
    if not producto.disponible or producto.stock <= 0:
        mensaje = f"No hay stock disponible de {producto.nombre}."
        if es_ajax:
            return JsonResponse({"error": mensaje}, status=409)
        request.session["mensaje_tienda"] = mensaje
        return redirect("sena:usuario_tienda")
    carrito = request.session.get("carrito", {})
    cantidad_actual = int(carrito.get(str(producto.id), 0))
    if cantidad_actual >= producto.stock:
        mensaje = f"No hay más unidades disponibles de {producto.nombre}."
        if es_ajax:
            return JsonResponse({"error": mensaje}, status=409)
        request.session["mensaje_tienda"] = mensaje
        return redirect("sena:usuario_tienda")
    carrito[str(producto.id)] = cantidad_actual + 1
    request.session["carrito"] = carrito
    if request.session.get("logueado"):
        request.session["carrito_usuario_id"] = request.session["logueado"]["id"]
    guardar_carrito_activo(request)
    if es_ajax:
        return JsonResponse({
            "cantidad": sum(int(c) for c in carrito.values()),
            "producto_id": producto.id,
            "mensaje": f"{producto.nombre} se agregó al carrito.",
        })
    messages.success(request, f"{producto.nombre} se agregó al carrito.")
    return redirect("sena:usuario_tienda")

def actualizar_carrito(request, producto_id):
    es_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not _cliente_o_invitado(request):
        if es_ajax:
            return JsonResponse({"error": "Solo los clientes pueden modificar el carrito."}, status=403)
        return redirect("sena:carrito")
    if not carrito_visible(request):
        if es_ajax:
            return JsonResponse({"error": "Este carrito no pertenece a la sesión actual."}, status=403)
        return redirect("sena:carrito")
    if request.method == "POST":
        try:
            cantidad = int(request.POST.get("cantidad", 1))
        except (TypeError, ValueError):
            cantidad = 1
        carrito = request.session.get("carrito", {})
        if str(producto_id) in carrito:
            producto = Producto.objects.filter(id=producto_id).first()
            stock = producto.stock if producto and producto.disponible else 0
            if cantidad > stock:
                cantidad = stock
                if producto:
                    request.session["mensaje_carrito"] = f"No hay suficiente stock de {producto.nombre}. Disponible: {stock}."
            if cantidad <= 0:
                del carrito[str(producto_id)]
            else:
                carrito[str(producto_id)] = cantidad
        request.session["carrito"] = carrito
        guardar_carrito_activo(request)
        if es_ajax:
            contexto = contexto_carrito(request)
            item = next((item for item in contexto["items"] if item["producto"].id == producto_id), None)
            return JsonResponse({
                "item_id": producto_id,
                "item_cantidad": item["cantidad"] if item else 0,
                "subtotal": item["subtotal"] if item else 0,
                "cantidad": contexto["cantidad"],
                "total": contexto["total"],
                "empty": not contexto["items"],
                "mensaje": contexto["mensaje_carrito"],
            })
        messages.success(request, "Carrito actualizado.")
    return redirect("sena:carrito")

def eliminar_carrito(request, producto_id):
    es_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not _cliente_o_invitado(request):
        if es_ajax:
            return JsonResponse({"error": "Solo los clientes pueden modificar el carrito."}, status=403)
        return redirect("sena:carrito")
    if not carrito_visible(request):
        if es_ajax:
            return JsonResponse({"error": "Este carrito no pertenece a la sesión actual."}, status=403)
        return redirect("sena:carrito")
    carrito = request.session.get("carrito", {})
    carrito.pop(str(producto_id), None)
    request.session["carrito"] = carrito
    guardar_carrito_activo(request)
    if es_ajax:
        contexto = contexto_carrito(request)
        return JsonResponse({
            "item_id": producto_id,
            "cantidad": contexto["cantidad"],
            "total": contexto["total"],
            "empty": not contexto["items"],
        })
    messages.info(request, "Producto eliminado del carrito.")
    return redirect("sena:carrito")

# COMPRA
@autorizacion(["Cliente"])
def finalizar_pedido(request):
    contexto = contexto_carrito(request)
    if not contexto["items"]:
        return redirect("sena:carrito")

    if request.method == "POST":
        cliente_id = request.session["logueado"]["id"]
        with transaction.atomic():
            producto_ids = [item["producto"].id for item in contexto["items"]]
            productos = {
                producto.id: producto
                for producto in Producto.objects.select_for_update().filter(id__in=producto_ids)
            }
            error_stock = ""
            for item in contexto["items"]:
                producto = productos.get(item["producto"].id)
                if producto is None or not producto.disponible or producto.stock < item["cantidad"]:
                    disponible = producto.stock if producto and producto.disponible else 0
                    nombre = producto.nombre if producto else item["producto"].nombre
                    error_stock = f"No hay stock suficiente de {nombre}. Disponible: {disponible}."
                    break
                item["producto"] = producto
                item["subtotal"] = producto.precio * item["cantidad"]

            if error_stock:
                contexto["error"] = error_stock
                return render(request, "carrito/finalizar_pedido.html", contexto)

            contexto["total"] = sum(item["subtotal"] for item in contexto["items"])
            pedido = Pedido.objects.create(
                cliente_id=cliente_id,
                total=contexto["total"],
                estado="Pendiente"
            )
            for item in contexto["items"]:
                producto = item["producto"]
                stock_anterior = producto.stock
                PedidoProducto.objects.create(
                    pedido=pedido,
                    producto=producto,
                    cantidad=item["cantidad"],
                    precio=producto.precio
                )
                producto.stock -= item["cantidad"]
                if producto.stock == 0:
                    producto.disponible = False
                    if stock_anterior > 0:
                        notificar_producto_agotado(producto)
                producto.save(update_fields=["stock", "disponible"])
        request.session["carrito"] = {}
        productos_resumen = ", ".join(f"{item['cantidad']} x {item['producto'].nombre}" for item in contexto["items"][:3])
        if len(contexto["items"]) > 3:
            productos_resumen += f" y {len(contexto['items']) - 3} productos más"
        Notificacion.objects.create(
            usuario_id=cliente_id,
            mensaje=f"Tu pedido #{pedido.id} fue recibido: {productos_resumen}. Total: ${pedido.total:,} COP.",
        )
        cliente = Usuario.objects.get(id=cliente_id)
        enviar_correo(
            cliente,
            f"Recibimos tu pedido #{pedido.id}",
            (
                f"Hola {cliente.nombre},\n\nRecibimos tu pedido #{pedido.id} por "
                f"${pedido.total:,} COP. Puedes pagarlo y recogerlo en la tienda. "
                "Te avisaremos cuando esté listo."
            ),
            request=request,
            enlace=request.build_absolute_uri(reverse("sena:usuario_perfil")),
            texto_enlace="Ver mis pedidos",
        )
        messages.success(request, f"Pedido #{pedido.id} recibido por ${pedido.total:,} COP. Pagarás al recogerlo en la tienda.")
        return redirect("sena:pedido_exitoso", pedido_id=pedido.id)

    return render(request, "carrito/finalizar_pedido.html", contexto)

@autorizacion(["Cliente"])
def pedido_exitoso(request, pedido_id):
    pedido = Pedido.objects.filter(id=pedido_id, cliente_id=request.session["logueado"]["id"]).first()
    if pedido is None:
        return redirect("sena:usuario_perfil")
    return render(request, "carrito/pedido_exitoso.html", {"pedido": pedido})

# ═══════════════════════════════════════════════════════════════════════════
# USUARIO/CLIENTE
# ═══════════════════════════════════════════════════════════════════════════

def usuario_dashboard(request):
    contexto = contexto_carrito(request)
    contexto["productos"] = Producto.objects.all()
    return render(request, "usuarios/usuario_tienda.html", contexto)

def usuario_tienda(request):
    contexto = contexto_carrito(request)
    contexto["productos"] = Producto.objects.all()
    return render(request, "usuarios/usuario_tienda.html", contexto)

def usuario_producto_detalle(request, id):
    contexto = contexto_carrito(request)
    contexto["producto"] = get_object_or_404(Producto, id=id)
    return render(request, "usuarios/usuario_producto_detalle.html", contexto)

def usuario_servicios(request):
    contexto = contexto_carrito(request)
    contexto["servicios"] = catalogo_servicios()
    return render(request, "usuarios/usuario_servicios.html", contexto)

def usuario_peluquerias(request):
    contexto = contexto_carrito(request)
    contexto["peluquerias"] = Peluqueria.objects.all()
    return render(request, "usuarios/usuario_peluquerias.html", contexto)

def usuario_peluqueria_detalle(request, id):
    contexto = contexto_carrito(request)
    peluqueria = get_object_or_404(Peluqueria, id=id)
    contexto["peluqueria"] = peluqueria
    contexto["fotos"] = peluqueria.galeria.all()
    return render(request, "usuarios/usuario_peluqueria_detalle.html", contexto)

def usuario_reservar_cita(request):
    contexto = contexto_carrito(request)
    contexto["peluqueros"] = barberos_disponibles()
    contexto["servicios"] = catalogo_servicios()
    servicio_inicial = request.GET.get("servicio", "").strip()
    contexto["servicio_inicial"] = servicio_inicial if servicio_valido(servicio_inicial) else ""
    peluqueria_id = _id_entero(request.GET.get("peluqueria"))
    peluqueria_inicial = Peluqueria.objects.filter(id=peluqueria_id).first() if peluqueria_id else None
    contexto["peluqueria_inicial"] = str(peluqueria_inicial.id) if peluqueria_inicial else ""
    contexto["peluqueria_inicial_obj"] = peluqueria_inicial
    # La vista se dedica por completo a la sede elegida: si viene una, solo se
    # ofrece esa; así no se muestran ni otras barberías ni sus datos.
    contexto["peluquerias"] = (
        Peluqueria.objects.filter(id=peluqueria_inicial.id)
        if peluqueria_inicial
        else Peluqueria.objects.all()
    )
    contexto.update(_horarios_para_template())
    contexto.update(_reservas_para_template())
    return render(request, "usuarios/usuario_reservar_cita.html", contexto)

@autorizacion(["Cliente"])
def usuario_pre_confirmar(request):
    if request.method != "POST":
        return redirect("sena:usuario_reservar_cita")
    peluquero_id = _id_entero(request.POST.get("peluquero"))
    peluqueria_id = _id_entero(request.POST.get("peluqueria"))
    peluquero = Usuario.objects.filter(id=peluquero_id, rol="Barbero", activo=True).first() if peluquero_id else None
    peluqueria = Peluqueria.objects.filter(id=peluqueria_id).first() if peluqueria_id else None
    fecha = request.POST.get("fecha", "")
    hora = request.POST.get("hora", "")
    servicio = request.POST.get("servicio", "").strip()
    datos_validos = peluquero is not None and peluqueria is not None and bool(fecha) and bool(hora) and servicio in {item["nombre"] for item in catalogo_servicios()}
    # El barbero debe pertenecer a la peluquería elegida.
    if datos_validos and peluquero.peluqueria_id != peluqueria.id:
        datos_validos = False
    disponible = datos_validos
    mensaje = ""
    if not datos_validos:
        mensaje = "Faltan datos o el barbero no pertenece a la barbería elegida. Completa todos los datos antes de continuar."
    if disponible:
        disponible, mensaje = cita_disponible(fecha, hora, peluqueria_id, servicio)
    if disponible:
        disponible, mensaje = barbero_esta_disponible(peluquero_id, fecha, hora, servicio)
    if not disponible:
        contexto = contexto_carrito(request)
        contexto.update({"error": mensaje, "peluqueros": barberos_disponibles(), "peluquerias": Peluqueria.objects.all(), "servicios": catalogo_servicios(), "servicio_inicial": servicio})
        contexto.update(_horarios_para_template())
        contexto.update(_reservas_para_template())
        return render(request, "usuarios/usuario_reservar_cita.html", contexto)
    datos = {
        "servicio": servicio,
        "peluquero": peluquero,
        "peluqueria": peluqueria,
        "fecha": fecha,
        "hora": hora,
        "duracion": minutos_servicio(servicio),
    }
    contexto = contexto_carrito(request)
    contexto["datos"] = datos
    return render(request, "usuarios/usuario_confirmar_reserva.html", contexto)

@autorizacion(["Cliente"])
def usuario_confirmar_reserva(request):
    if request.method != "POST":
        return redirect("sena:usuario_reservar_cita")
    peluquero_id = _id_entero(request.POST.get("peluquero"))
    peluqueria_id = _id_entero(request.POST.get("peluqueria"))
    peluquero = Usuario.objects.filter(id=peluquero_id, rol="Barbero", activo=True).first() if peluquero_id else None
    peluqueria = Peluqueria.objects.filter(id=peluqueria_id).first() if peluqueria_id else None
    fecha = request.POST.get("fecha", "").strip()
    hora = request.POST.get("hora", "").strip()
    servicio = request.POST.get("servicio", "").strip()
    datos_validos = peluquero is not None and peluqueria is not None and bool(fecha) and bool(hora) and servicio in {item["nombre"] for item in catalogo_servicios()}
    # El barbero debe pertenecer a la peluquería elegida.
    if datos_validos and peluquero.peluqueria_id != peluqueria.id:
        datos_validos = False
    disponible = datos_validos
    mensaje = ""
    if not datos_validos:
        disponible = False
        mensaje = "Faltan datos o el barbero no pertenece a la barbería elegida. Elige servicio, barbero, barbería, fecha y hora antes de confirmar."
    if disponible:
        disponible, mensaje = cita_disponible(fecha, hora, peluqueria_id, servicio)
    if disponible:
        disponible, mensaje = barbero_esta_disponible(peluquero_id, fecha, hora, servicio)
    if not disponible:
        contexto = contexto_carrito(request)
        contexto.update({"error": mensaje, "peluqueros": barberos_disponibles(), "peluquerias": Peluqueria.objects.all(), "servicios": catalogo_servicios(), "servicio_inicial": servicio})
        contexto.update(_horarios_para_template())
        contexto.update(_reservas_para_template())
        return render(request, "usuarios/usuario_reservar_cita.html", contexto)
    with transaction.atomic():
        Usuario.objects.select_for_update().get(id=peluquero_id)
        disponible, mensaje = cita_disponible(fecha, hora, peluqueria_id, servicio)
        if disponible:
            disponible, mensaje = barbero_esta_disponible(peluquero_id, fecha, hora, servicio)
        if not disponible:
            contexto = contexto_carrito(request)
            contexto.update({"error": mensaje, "peluqueros": barberos_disponibles(), "peluquerias": Peluqueria.objects.all(), "servicios": catalogo_servicios(), "servicio_inicial": servicio})
            contexto.update(_horarios_para_template())
            contexto.update(_reservas_para_template())
            return render(request, "usuarios/usuario_reservar_cita.html", contexto)
        reserva = Reserva.objects.create(
            cliente_id=request.session["logueado"]["id"],
            peluquero_id=peluquero_id,
            peluqueria_id=peluqueria_id,
            fecha=fecha,
            hora=hora,
            servicio=servicio
        )
    Notificacion.objects.create(
        usuario_id=reserva.peluquero_id,
        reserva=reserva,
        mensaje=f"Nueva cita: {reserva.cliente.nombre} {reserva.cliente.apellido} reservó {reserva.servicio} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.",
    )
    Notificacion.objects.create(
        usuario_id=reserva.cliente_id,
        reserva=reserva,
        mensaje=f"Tu cita de {reserva.servicio} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre} con el barbero {reserva.peluquero.nombre} {reserva.peluquero.apellido} fue reservada correctamente.",
    )
    enviar_correo_cita(
        request,
        reserva.cliente,
        "Cita agendada en TecnoCorte",
        f"Hola {reserva.cliente.nombre},\n\nTu cita de {reserva.servicio} quedó agendada para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.",
        request.build_absolute_uri(reverse("sena:usuario_editar_reserva", args=[reserva.id])),
    )
    enviar_correo_cita(
        request,
        reserva.peluquero,
        "Nueva cita agendada en TecnoCorte",
        f"Tienes una nueva cita con {reserva.cliente.nombre} {reserva.cliente.apellido} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.",
        request.build_absolute_uri(reverse("sena:peluquero_dashboard")),
    )
    _invalidar_cache_disponibilidad()
    messages.success(request, "Cita reservada correctamente. El barbero ya fue notificado.")
    return redirect("sena:inicio")

@autorizacion(["Cliente"])
def usuario_perfil(request):
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    if request.method == "POST":
        telefono = request.POST.get("telefono", usuario.telefono).strip()
        error_telefono = validar_telefono(telefono)
        if error_telefono:
            messages.error(request, error_telefono)
            return redirect("sena:usuario_perfil")
        foto = request.FILES.get("foto")
        error_imagen = validar_imagen(foto)
        if error_imagen:
            messages.error(request, error_imagen)
            return redirect("sena:usuario_perfil")
        usuario.nombre = request.POST.get("nombre", usuario.nombre)
        usuario.apellido = request.POST.get("apellido", usuario.apellido)
        usuario.telefono = telefono
        if foto:
            usuario.foto = foto
        usuario.save()
        enviar_correo(
            usuario,
            "Tu perfil fue actualizado",
            f"Hola {usuario.nombre},\n\nTus datos de perfil fueron actualizados correctamente en TecnoCorte.",
            request=request,
            enlace=request.build_absolute_uri(reverse("sena:usuario_perfil")),
            texto_enlace="Revisar mi perfil",
        )
        messages.success(request, "Perfil actualizado correctamente.")
        return redirect("sena:usuario_perfil")
    citas = Reserva.objects.select_related("peluquero", "peluqueria").filter(cliente=usuario).order_by("-fecha", "-hora")
    pedidos = Pedido.objects.filter(cliente=usuario).prefetch_related("productos__producto").order_by("-fecha")
    calificaciones_reservas = set(Calificacion.objects.filter(cliente=usuario).values_list("reserva_id", flat=True))
    contexto = contexto_carrito(request)
    contexto["usuario"] = usuario
    contexto["citas"] = citas
    contexto["pedidos"] = pedidos
    contexto["notificaciones"] = Notificacion.objects.filter(usuario=usuario).order_by("-fecha")
    contexto["calificaciones_reservas"] = calificaciones_reservas
    contexto["resenas_restantes"] = resenas_restantes(usuario.id)
    contexto["resenas_por_persona"] = RESENAS_POR_PERSONA
    return render(request, "usuarios/usuario_perfil.html", contexto)


@autorizacion(["Cliente"])
def usuario_cancelar_reserva(request, reserva_id):
    reserva = Reserva.objects.filter(id=reserva_id, cliente_id=request.session["logueado"]["id"]).first()
    if reserva is None or request.method != "POST":
        return redirect("sena:usuario_perfil")
    fecha_cita = datetime.combine(reserva.fecha, reserva.hora)
    ahora = timezone.localtime().replace(tzinfo=None)
    if fecha_cita - ahora >= timedelta(hours=2):
        reserva.estado = "Cancelada"
        reserva.save()
        Notificacion.objects.create(usuario=reserva.peluquero, reserva=reserva, mensaje=f"El cliente canceló la cita del {formato_cita(reserva)}.")
        enviar_correo_cita(request, reserva.peluquero, "Cita cancelada en TecnoCorte", f"La cita de {reserva.cliente.nombre} del {formato_cita(reserva)} fue cancelada por el cliente.")
        enviar_correo_cita(request, reserva.cliente, "Cancelación de cita en TecnoCorte", f"Tu cita del {formato_cita(reserva)} fue cancelada correctamente.")
        messages.success(request, "La cita fue cancelada y el barbero ha sido notificado.")
    else:
        Notificacion.objects.create(usuario=reserva.cliente, reserva=reserva, mensaje=f"La cita está muy próxima para cancelarla en línea. Contacta al barbero: {reserva.peluquero.telefono or 'teléfono no registrado'}.")
        messages.warning(request, "La cita está muy próxima para cancelarla en línea.")
    _invalidar_cache_disponibilidad()
    return redirect("sena:usuario_perfil")


@autorizacion(["Cliente"])
def usuario_editar_reserva(request, reserva_id):
    reserva = Reserva.objects.filter(id=reserva_id, cliente_id=request.session["logueado"]["id"]).first()
    if reserva is None or reserva.estado in ["Cancelada", "Completada"]:
        return redirect("sena:usuario_perfil")
    if request.method == "POST":
        fecha = request.POST.get("fecha", "").strip()
        hora = request.POST.get("hora", "").strip()
        servicio = request.POST.get("servicio", "").strip()
        # Los ids se validan como enteros para evitar errores con valores no numéricos
        barbero_id = _id_entero(request.POST.get("peluquero"))
        peluqueria_id = _id_entero(request.POST.get("peluqueria"))
        barbero = Usuario.objects.filter(id=barbero_id, rol="Barbero", activo=True).first() if barbero_id else None
        peluqueria = Peluqueria.objects.filter(id=peluqueria_id).first() if peluqueria_id else None
        disponible = bool(barbero and peluqueria and servicio in {item["nombre"] for item in catalogo_servicios()})
        mensaje = None
        if barbero and peluqueria and barbero.peluqueria_id != peluqueria.id:
            disponible, mensaje = False, "El barbero elegido no pertenece a la barbería seleccionada."
        if disponible:
            disponible, mensaje = cita_disponible(fecha, hora, peluqueria.id, servicio)
        if disponible and barbero:
            disponible, mensaje = barbero_esta_disponible(barbero.id, fecha, hora, servicio, reserva)
        if disponible:
            barbero_anterior = reserva.peluquero
            reserva.fecha, reserva.hora, reserva.servicio = fecha, hora, servicio
            reserva.peluquero, reserva.peluqueria = barbero, peluqueria
            reserva.estado = "Pendiente"
            # Una cita reprogramada necesita un nuevo recordatorio aunque ya
            # se hubiera enviado el de la fecha anterior.
            reserva.recordatorio_correo_enviado = None
            reserva.save()
            Notificacion.objects.create(usuario=barbero, reserva=reserva, mensaje=f"Una cita fue modificada para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.")
            Notificacion.objects.create(usuario=reserva.cliente, reserva=reserva, mensaje=f"Tu cita de {reserva.servicio} fue modificada para el {formato_cita(reserva)} en {reserva.peluqueria.nombre} y quedó pendiente de confirmación.")
            enviar_correo_cita(
                request,
                reserva.cliente,
                "Tu cita fue modificada en TecnoCorte",
                f"Hola {reserva.cliente.nombre},\n\nTu cita de {reserva.servicio} fue modificada para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.",
                request.build_absolute_uri(reverse("sena:usuario_editar_reserva", args=[reserva.id])),
            )
            enviar_correo_cita(request, barbero, "Cita modificada en TecnoCorte", f"La cita de {reserva.cliente.nombre} fue modificada para el {formato_cita(reserva)}.")
            if barbero_anterior.id != barbero.id:
                Notificacion.objects.create(usuario=barbero_anterior, reserva=reserva, mensaje=f"La cita del {formato_cita(reserva)} fue reasignada a otro barbero.")
            _invalidar_cache_disponibilidad()
            messages.success(request, "La cita fue modificada correctamente.")
            return redirect("sena:usuario_perfil")
        return render(request, "usuarios/usuario_editar_reserva.html", {"reserva": reserva, "peluqueros": barberos_disponibles(), "peluquerias": Peluqueria.objects.all(), "servicios": catalogo_servicios(), "error": mensaje or "Datos inválidos."})
    return render(request, "usuarios/usuario_editar_reserva.html", {"reserva": reserva, "peluqueros": barberos_disponibles(), "peluquerias": Peluqueria.objects.all(), "servicios": catalogo_servicios()})

@autorizacion(["Cliente"])
def usuario_notificaciones(request):
    contexto = contexto_carrito(request)
    contexto["notificaciones"] = Notificacion.objects.filter(
        usuario_id=request.session["logueado"]["id"]
    ).order_by("-fecha")
    contexto["calificaciones_reservas"] = set(
        Calificacion.objects.filter(cliente_id=request.session["logueado"]["id"]).values_list("reserva_id", flat=True)
    )
    contexto["resenas_restantes"] = resenas_restantes(request.session["logueado"]["id"])
    return render(request, "usuarios/usuario_notificaciones.html", contexto)


@autorizacion(["Cliente"])
def usuario_marcar_notificaciones_leidas(request):
    if request.method == "POST":
        Notificacion.objects.filter(usuario_id=request.session["logueado"]["id"], leida=False).update(leida=True)
        messages.success(request, "Todas tus notificaciones están marcadas como leídas.")
    return redirect("sena:usuario_notificaciones")

@autorizacion(["Cliente"])
def usuario_confirmar_cita_peluquero(request, reserva_id):
    if request.method != "POST":
        return redirect("sena:usuario_notificaciones")
    reserva = Reserva.objects.filter(
        id=reserva_id, cliente_id=request.session["logueado"]["id"], estado="Pendiente", peluquero__activo=True
    ).first()
    if reserva is None:
        return redirect("sena:usuario_notificaciones")
    reserva.estado = "Confirmada"
    reserva.save()
    Notificacion.objects.filter(
        usuario_id=request.session["logueado"]["id"], reserva=reserva
    ).update(leida=True)
    Notificacion.objects.create(
        usuario=reserva.peluquero,
        reserva=reserva,
        mensaje=f"El cliente confirmó la cita del {formato_cita(reserva)}.",
    )
    enviar_correo_cita(
        request,
        reserva.peluquero,
        "Cita confirmada por el cliente",
        f"{reserva.cliente.nombre} {reserva.cliente.apellido} confirmó la cita de {reserva.servicio} para el {formato_cita(reserva)}.",
        request.build_absolute_uri(reverse("sena:peluquero_dashboard")),
    )
    enviar_correo_cita(
        request,
        reserva.cliente,
        "Tu cita quedó confirmada",
        f"Tu cita de {reserva.servicio} para el {formato_cita(reserva)} quedó confirmada correctamente.",
        request.build_absolute_uri(reverse("sena:usuario_perfil")),
    )
    messages.success(request, "Cita confirmada. Te esperamos en TecnoCorte.")
    return redirect("sena:usuario_notificaciones")

@autorizacion(["Cliente"])
def usuario_calificar(request, reserva_id):
    if request.method != "POST":
        return redirect("sena:usuario_perfil")
    cliente_id = request.session["logueado"]["id"]
    if resenas_restantes(cliente_id) <= 0:
        messages.error(request, f"Ya publicaste tus {RESENAS_POR_PERSONA} reseñas permitidas.")
        return redirect("sena:usuario_perfil")
    reserva = Reserva.objects.filter(id=reserva_id, cliente_id=cliente_id, estado="Completada").first()
    if reserva is None:
        return redirect("sena:usuario_perfil")
    if Calificacion.objects.filter(reserva=reserva).exists():
        return redirect("sena:usuario_perfil")
    try:
        puntuacion = int(request.POST.get("puntuacion", 0))
    except (TypeError, ValueError):
        puntuacion = 0
    if puntuacion < 1 or puntuacion > 5:
        return redirect("sena:usuario_perfil")
    Calificacion.objects.create(
        reserva=reserva,
        cliente_id=cliente_id,
        barbero=reserva.peluquero,
        puntuacion=puntuacion,
        comentario=request.POST.get("comentario", "").strip(),
    )
    Notificacion.objects.create(
        usuario=reserva.peluquero,
        reserva=reserva,
        mensaje=f"Recibiste una calificación de {puntuacion}/5 estrellas por tu servicio del {reserva.fecha}.",
    )
    messages.success(request, "Gracias por calificar tu experiencia.")
    return redirect("sena:usuario_perfil")


@autorizacion(["Cliente", "Barbero"])
def cambiar_password(request):
    rol = request.session["logueado"]["rol"]
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    destino = "sena:usuario_perfil" if rol == "Cliente" else "sena:peluquero_perfil"
    if request.method == "POST":
        actual = request.POST.get("password_actual", "")
        nueva = request.POST.get("password", "")
        confirmacion = request.POST.get("password_confirm", "")
        error = ""
        if not check_password(actual, usuario.password):
            error = "La contraseña actual no es correcta."
        elif nueva != confirmacion:
            error = "Las contraseñas nuevas no coinciden."
        else:
            error = validar_password(nueva)
        if error:
            return render(request, "usuarios/cambiar_password.html", {"rol": rol, "usuario": usuario, "error": error})
        usuario.password = make_password(nueva)
        # Invalida todas las sesiones anteriores y conserva únicamente esta
        # sesión recién validada con la nueva versión.
        usuario.sesion_version += 1
        usuario.save(update_fields=["password", "sesion_version"])
        request.session["logueado"] = {
            **request.session["logueado"],
            "sesion_version": usuario.sesion_version,
        }
        request.session.cycle_key()
        registrar_accion(request, "cambio_contrasena", "Usuario", usuario.id)
        enviar_correo(
            usuario,
            "Tu contraseña fue actualizada",
            f"Hola {usuario.nombre},\n\nLa contraseña de tu cuenta de TecnoCorte fue actualizada correctamente. Si no hiciste este cambio, contacta al equipo de soporte.",
            request=request,
            enlace=request.build_absolute_uri(reverse(destino)),
            texto_enlace="Ir a mi cuenta",
        )
        messages.success(request, "Contraseña actualizada correctamente.")
        return redirect(destino)
    return render(request, "usuarios/cambiar_password.html", {"rol": rol, "usuario": usuario})

# ═══════════════════════════════════════════════════════════════════════════
# PELUQUERO
# ═══════════════════════════════════════════════════════════════════════════

@autorizacion(["Barbero"])
def peluquero_dashboard(request):
    barbero_id = request.session["logueado"]["id"]
    peluqueria = _peluqueria_del_barbero(barbero_id)
    precios = {item["nombre"]: item["precio"] for item in catalogo_servicios()}
    # Las métricas agregadas se cachean 20 s para no pagar la latencia en cada recarga.
    clave_metricas = f"barbero_dashboard_metricas_{barbero_id}"
    metricas = cache.get(clave_metricas)
    if metricas is None:
        citas = list(Reserva.objects.select_related("cliente", "peluqueria").filter(peluquero_id=barbero_id))
        hoy = timezone.localdate()
        citas_completadas = [c for c in citas if c.estado == "Completada"]
        citas_pendientes = [c for c in citas if c.estado == "Pendiente"]
        citas_canceladas = [c for c in citas if c.estado == "Cancelada"]
        citas_hoy = [c for c in citas if c.fecha == hoy]
        metricas = {"citas": citas, "citas_completadas": citas_completadas, "citas_pendientes": citas_pendientes,
                    "citas_canceladas": citas_canceladas, "citas_hoy": citas_hoy,
                    "ingresos_hoy": sum(precios.get(c.servicio, 0) for c in citas_hoy if c.estado == "Completada"),
                    "ingresos_total": sum(precios.get(c.servicio, 0) for c in citas_completadas),
                    "total_citas": len(citas)}
        cache.set(clave_metricas, metricas, 20)
    contexto = dict(metricas)
    todas_califs = list(Calificacion.objects.select_related("cliente").filter(barbero_id=barbero_id))
    todas_califs.sort(key=lambda c: c.fecha, reverse=True)
    contexto["calificaciones"] = todas_califs[:5]
    contexto["promedio"] = round(sum(c.puntuacion for c in todas_califs) / len(todas_califs), 1) if todas_califs else 0
    contexto["total_calificaciones"] = len(todas_califs)
    contexto["peluqueria"] = peluqueria
    contexto["fotos"] = peluqueria.galeria.all() if peluqueria else []
    hoy = timezone.localdate()
    contexto["proxima_cita"] = next(
        (cita for cita in sorted(contexto["citas"], key=lambda c: (c.fecha, c.hora, c.id))
         if (cita.fecha > hoy or (cita.fecha == hoy and cita.hora >= timezone.localtime().time()))
         and cita.estado in {"Pendiente", "Confirmada"}),
        None,
    )
    return render(request, "peluqueros/peluquero_dashboard.html", contexto)

@autorizacion(["Barbero"])
def peluquero_cambiar_estado(request, cita_id):
    if request.method != "POST":
        return redirect("sena:peluquero_dashboard")
    cita = Reserva.objects.filter(id=cita_id, peluquero_id=request.session["logueado"]["id"]).first()
    if cita is None:
        return redirect("sena:peluquero_dashboard")
    nuevo_estado = request.POST.get("estado", "")
    estados_validos = [e[0] for e in Reserva.ESTADOS]
    if nuevo_estado in estados_validos:
        estado_anterior = cita.estado
        if not transicion_valida(TRANSICIONES_RESERVA, estado_anterior, nuevo_estado):
            messages.error(request, f"No se puede pasar una cita de {estado_anterior} a {nuevo_estado}.")
            return redirect("sena:peluquero_dashboard")
        cita.estado = nuevo_estado
        cita.save()
        registrar_accion(request, "actualizar_cita", "Reserva", cita.id, f"Estado: {estado_anterior} → {nuevo_estado}")
        # Las métricas del dashboard se recalculan con datos frescos (invalidar la caché corta).
        cache.delete(f"barbero_dashboard_metricas_{cita.peluquero_id}")
        cache.delete("admin_dashboard_metricas")
        _invalidar_cache_disponibilidad()
        if nuevo_estado != estado_anterior:
            mensajes_estado = {
                "Confirmada": f"Tu cita de {cita.servicio} del {formato_cita(cita)} fue confirmada por el barbero.",
                "Completada": f"Tu cita de {cita.servicio} del {formato_cita(cita)} fue marcada como completada. ¡Califica tu experiencia!",
                "Cancelada": f"Tu cita de {cita.servicio} del {formato_cita(cita)} fue cancelada por el barbero.",
                "Pendiente": f"Tu cita de {cita.servicio} del {formato_cita(cita)} volvió a estar pendiente.",
            }
            Notificacion.objects.create(
                usuario=cita.cliente,
                reserva=cita,
                mensaje=mensajes_estado.get(nuevo_estado, f"El estado de tu cita cambió a {nuevo_estado}."),
            )
            if nuevo_estado == "Cancelada":
                enviar_correo_cita(request, cita.cliente, "Cita cancelada en TecnoCorte", f"Tu cita de {cita.servicio} del {formato_cita(cita)} fue cancelada por el barbero.")
            elif nuevo_estado == "Confirmada":
                enviar_correo_cita(request, cita.cliente, "Cita confirmada en TecnoCorte", f"Tu cita de {cita.servicio} del {formato_cita(cita)} fue confirmada por el barbero.")
            elif nuevo_estado == "Completada":
                enviar_correo_cita(
                    request,
                    cita.cliente,
                    "Tu cita fue completada en TecnoCorte",
                    f"Tu cita de {cita.servicio} del {formato_cita(cita)} fue marcada como completada. Ya puedes dejar tu calificación desde tu perfil.",
                    request.build_absolute_uri(reverse("sena:usuario_perfil")),
                )
            messages.success(request, f"Cita actualizada a {nuevo_estado.lower()}.")
    return redirect("sena:peluquero_dashboard")

@autorizacion(["Barbero"])
def peluquero_perfil(request):
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    if request.method == "POST":
        telefono = request.POST.get("telefono", usuario.telefono).strip()
        error_telefono = validar_telefono(telefono)
        if error_telefono:
            messages.error(request, error_telefono)
            return redirect("sena:peluquero_perfil")
        foto = request.FILES.get("foto")
        error_imagen = validar_imagen(foto)
        if error_imagen:
            messages.error(request, error_imagen)
            return redirect("sena:peluquero_perfil")
        usuario.nombre = request.POST.get("nombre", usuario.nombre)
        usuario.apellido = request.POST.get("apellido", usuario.apellido)
        usuario.telefono = telefono
        if foto:
            usuario.foto = foto
        usuario.save()
        enviar_correo(
            usuario,
            "Tu perfil de barbero fue actualizado",
            f"Hola {usuario.nombre},\n\nTus datos de perfil fueron actualizados correctamente en TecnoCorte.",
            request=request,
            enlace=request.build_absolute_uri(reverse("sena:peluquero_perfil")),
            texto_enlace="Revisar mi perfil",
        )
        messages.success(request, "Perfil actualizado correctamente.")
        return redirect("sena:peluquero_perfil")
    citas = Reserva.objects.select_related("cliente", "peluqueria").filter(peluquero=usuario).order_by("-fecha", "-hora")
    calificaciones = Calificacion.objects.select_related("cliente").filter(barbero=usuario)
    # Resumen en una sola consulta en lugar de dos.
    resumen = calificaciones.aggregate(promedio=models.Avg("puntuacion"), totales=models.Count("id"))
    promedio = round(resumen["promedio"], 1) if resumen["promedio"] is not None else 0
    contexto = {
        "usuario": usuario,
        "citas": citas,
        "calificaciones": calificaciones,
        "promedio": promedio,
        "total_calificaciones": resumen["totales"],
    }
    return render(request, "peluqueros/peluquero_perfil.html", contexto)

@autorizacion(["Barbero"])
def peluquero_crear_cita(request):
    if request.method == "POST":
        # Los ids se validan como enteros para evitar errores con valores no numéricos
        cliente_id = _id_entero(request.POST.get("cliente"))
        peluqueria_id = _id_entero(request.POST.get("peluqueria"))
        cliente = Usuario.objects.filter(id=cliente_id, rol="Cliente").first() if cliente_id else None
        peluqueria = Peluqueria.objects.filter(id=peluqueria_id).first() if peluqueria_id else None
        if cliente is None or peluqueria is None:
            return render(request, "peluqueros/peluquero_crear_cita.html", {
                "clientes": Usuario.objects.filter(rol="Cliente"),
                "peluquerias": Peluqueria.objects.all(),
                "servicios": catalogo_servicios(),
                "reserva_estados": Reserva.ESTADOS,
                "error": "Selecciona un cliente y una peluquería válidos.",
            })
        disponible, mensaje = cita_disponible(request.POST.get("fecha"), request.POST.get("hora"), peluqueria.id, request.POST.get("servicio"))
        if disponible:
            disponible, mensaje = barbero_esta_disponible(request.session["logueado"]["id"], request.POST.get("fecha"), request.POST.get("hora"), request.POST.get("servicio"))
        if not disponible:
            contexto = {"clientes": Usuario.objects.filter(rol="Cliente"), "peluquerias": Peluqueria.objects.all(), "servicios": catalogo_servicios(), "reserva_estados": Reserva.ESTADOS, "error": mensaje}
            return render(request, "peluqueros/peluquero_crear_cita.html", contexto)
        reserva = Reserva.objects.create(
            cliente=cliente,
            peluquero_id=request.session["logueado"]["id"],
            peluqueria=peluqueria,
            fecha=request.POST.get("fecha"),
            hora=request.POST.get("hora"),
            servicio=request.POST.get("servicio", "Corte de Cabello"),
            estado="Pendiente",
        )
        Notificacion.objects.create(
            usuario=cliente,
            reserva=reserva,
            mensaje=f"El barbero {request.session['logueado']['nombre']} agendó una cita de {reserva.servicio} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}. Confírmala desde tu cuenta.",
        )
        enviar_correo_cita(
            request,
            cliente,
            "Cita agendada por tu barbero en TecnoCorte",
            f"El barbero {request.session['logueado']['nombre']} agendó tu cita de {reserva.servicio} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.",
            request.build_absolute_uri(reverse("sena:usuario_editar_reserva", args=[reserva.id])),
        )
        messages.success(request, "La cita fue agendada y el cliente recibió una notificación.")
        return redirect("sena:peluquero_dashboard")
    contexto = {
        "clientes": Usuario.objects.filter(rol="Cliente"),
        "peluquerias": Peluqueria.objects.all(),
        "servicios": catalogo_servicios(),
        "reserva_estados": Reserva.ESTADOS,
    }
    return render(request, "peluqueros/peluquero_crear_cita.html", contexto)


@autorizacion(["Barbero"])
def peluquero_notificaciones(request):
    notificaciones = Notificacion.objects.filter(usuario_id=request.session["logueado"]["id"]).order_by("-fecha")
    notificaciones.update(leida=True)
    return render(request, "peluqueros/peluquero_notificaciones.html", {"notificaciones": notificaciones})


# ═══════════════════════════════════════════════════════════════════════════
# PELUQUERÍA DEL BARBERO
# ═══════════════════════════════════════════════════════════════════════════

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


@autorizacion(["Barbero"])
def peluquero_editar_peluqueria(request):
    peluqueria = _peluqueria_del_barbero(request.session["logueado"]["id"])
    if not peluqueria:
        messages.info(request, SIN_PELUQUERIA)
        return redirect("sena:peluquero_dashboard")
    if request.method == "POST":
        imagen = request.FILES.get("imagen")
        error_imagen = validar_imagen(imagen)
        if error_imagen:
            messages.error(request, error_imagen)
            return redirect("sena:peluquero_editar_peluqueria")
        peluqueria.nombre = request.POST.get("nombre", peluqueria.nombre).strip()
        peluqueria.ubicacion = request.POST.get("ubicacion", peluqueria.ubicacion).strip()
        peluqueria.telefono = request.POST.get("telefono", peluqueria.telefono).strip()
        peluqueria.descripcion = request.POST.get("descripcion", peluqueria.descripcion).strip()
        if imagen:
            peluqueria.imagen = imagen
        peluqueria.save()
        messages.success(request, "Peluquería actualizada.")
        return redirect("sena:peluquero_editar_peluqueria")
    return render(request, "peluqueros/peluquero_editar_peluqueria.html", {"peluqueria": peluqueria})


@autorizacion(["Barbero"])
def peluquero_galeria(request):
    peluqueria = _peluqueria_del_barbero(request.session["logueado"]["id"])
    if not peluqueria:
        messages.info(request, SIN_PELUQUERIA)
        return redirect("sena:peluquero_dashboard")
    fotos = peluqueria.galeria.all()
    return render(request, "peluqueros/peluquero_galeria.html", {"peluqueria": peluqueria, "fotos": fotos})


@autorizacion(["Barbero"])
def peluquero_agregar_imagen(request):
    peluqueria = _peluqueria_del_barbero(request.session["logueado"]["id"])
    if not peluqueria:
        messages.info(request, SIN_PELUQUERIA)
        return redirect("sena:peluquero_dashboard")
    if request.method == "POST":
        if peluqueria.galeria.count() >= 5:
            messages.error(request, "La galería tiene un máximo de 5 fotos. Elimina una antes de subir otra.")
            return redirect("sena:peluquero_galeria")
        imagen = request.FILES.get("imagen")
        error_imagen = validar_imagen(imagen)
        if error_imagen:
            messages.error(request, error_imagen)
            return redirect("sena:peluquero_galeria")
        if imagen:
            ImagenPeluqueria.objects.create(
                peluqueria=peluqueria,
                imagen=imagen,
                descripcion=request.POST.get("descripcion", "").strip(),
            )
            messages.success(request, "Foto agregada a la galería.")
    return redirect("sena:peluquero_galeria")


@autorizacion(["Barbero"])
def peluquero_eliminar_imagen(request, imagen_id):
    foto = ImagenPeluqueria.objects.filter(id=imagen_id, peluqueria__dueno_id=request.session["logueado"]["id"]).first()
    if foto:
        if foto.imagen:
            foto.imagen.delete(save=False)
        foto.delete()
        messages.success(request, "Foto eliminada.")
    return redirect("sena:peluquero_galeria")

# ═══════════════════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════════════════

@autorizacion(["Admin"])
def admin_dashboard(request):
    # Métricas agregadas con caché corta (20 s): la BD remota paga ~90 ms por consulta.
    clave = "admin_dashboard_metricas"
    metricas = cache.get(clave)
    if metricas is None:
        precios = {item["nombre"]: item["precio"] for item in catalogo_servicios()}
        todas_reservas = list(Reserva.objects.select_related("cliente", "peluquero"))
        total_reservas = len(todas_reservas)
        estados = {estado[0]: sum(1 for r in todas_reservas if r.estado == estado[0]) for estado in Reserva.ESTADOS}
        ventas_servicios = sum(precios.get(r.servicio, 0) for r in todas_reservas if r.estado == "Completada")
        # Solo se contabilizan pedidos pagados en la tienda; un pedido
        # pendiente todavía no representa un ingreso confirmado.
        ventas_productos = sum(
            pedido.total
            for pedido in Pedido.objects.filter(pago_confirmado=True).exclude(estado="Cancelado")
        )
        total = ventas_servicios + ventas_productos
        maximo = max(estados.values()) if any(estados.values()) else 1
        total_clientes = Usuario.objects.filter(rol="Cliente").count()
        citas_hoy = sum(1 for reserva in todas_reservas if reserva.fecha == timezone.localdate())
        pedidos_pendientes = Pedido.objects.filter(estado="Pendiente").count()
        ultimas = sorted(todas_reservas, key=lambda r: (r.fecha, r.hora, r.id), reverse=True)[:6]
        metricas = {"total": total, "ventas_servicios": ventas_servicios, "ventas_productos": ventas_productos, "total_reservas": total_reservas, "total_clientes": total_clientes, "citas_hoy": citas_hoy, "pedidos_pendientes": pedidos_pendientes, "estados": estados, "maximo": maximo, "ultimas_reservas": ultimas}
        cache.set(clave, metricas, 20)
    return render(request, "administrador/admin_dashboard.html", metricas)

@autorizacion(["Admin"])
def admin_exportar_reservas(request):
    """Descarga un reporte compatible con Excel de todas las reservas."""
    reservas = Reserva.objects.select_related("cliente", "peluquero", "peluqueria").order_by("fecha", "hora")
    filas = [(r.id, f"{r.fecha:%d/%m/%Y}", f"{r.hora:%H:%M}", f"{r.cliente.nombre} {r.cliente.apellido}", f"{r.peluquero.nombre} {r.peluquero.apellido}", r.peluqueria.nombre, r.servicio, r.estado) for r in reservas]
    respuesta = _respuesta_reporte_excel("Reporte de reservas · TecnoCorte", "Reservas registradas", ["ID", "Fecha", "Hora", "Cliente", "Barbero", "Barbería", "Servicio", "Estado"], filas, "reservas_tecnocorte.xls")
    return respuesta

@autorizacion(["Admin"])
def admin_exportar_pedidos(request):
    """Descarga un reporte compatible con Excel de los pedidos."""
    pedidos = Pedido.objects.select_related("cliente").order_by("-fecha")
    filas = [(p.id, f"{p.fecha:%d/%m/%Y %H:%M}", f"{p.cliente.nombre} {p.cliente.apellido}", p.cliente.email, p.total, p.estado, "Sí" if p.pago_confirmado else "No") for p in pedidos]
    return _respuesta_reporte_excel("Reporte de pedidos · TecnoCorte", "Pedidos registrados", ["ID", "Fecha", "Cliente", "Correo", "Total COP", "Estado", "Pago confirmado"], filas, "pedidos_tecnocorte.xls")

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
    <div class="meta">Generado por TecnoCorte · Registros: <strong>{len(filas)}</strong></div>
    <table><thead><tr>{encabezados_html}</tr></thead><tbody>{filas_html}</tbody></table></div></body></html>"""
    respuesta = HttpResponse("\ufeff" + html, content_type="application/vnd.ms-excel; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    return respuesta

@autorizacion(["Admin"])
def admin_peluqueros(request):
    peluqueros = Usuario.objects.filter(rol="Barbero")
    return render(request, "administrador/admin_listar_peluqueros.html", {"datos": peluqueros, "puede_gestionar_roles": puede_gestionar_roles(request)})

@autorizacion(["Admin"])
def admin_crear_peluquero(request):
    if request.method == "POST" and not puede_gestionar_roles(request):
        messages.error(request, "Solo el administrador principal puede crear usuarios con rol Barbero.")
        return redirect("sena:admin_peluqueros")
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        peluqueria_id = _id_entero(request.POST.get("peluqueria"))
        if not all([nombre, apellido, email, password]):
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": "Completa todos los campos obligatorios.", "peluquerias": Peluqueria.objects.all()})
        try:
            validate_email(email)
        except ValidationError:
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": "Ese correo no tiene un formato válido.", "peluquerias": Peluqueria.objects.all()})
        error_password = validar_password(password)
        if error_password:
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": error_password, "peluquerias": Peluqueria.objects.all()})
        if Usuario.objects.filter(email=email).exists():
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": "Ya existe un usuario con ese correo.", "peluquerias": Peluqueria.objects.all()})
        if not peluqueria_id or not Peluqueria.objects.filter(id=peluqueria_id).exists():
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": "Selecciona la barbería a la que pertenece el barbero.", "peluquerias": Peluqueria.objects.all()})
        foto = request.FILES.get("foto")
        error_telefono = validar_telefono(request.POST.get("telefono", "").strip())
        error_imagen = validar_imagen(foto)
        if error_telefono or error_imagen:
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": error_telefono or error_imagen, "peluquerias": Peluqueria.objects.all()})
        barbero = Usuario.objects.create(nombre=nombre, apellido=apellido, email=email, password=make_password(password), telefono=request.POST.get("telefono", "").strip(), rol="Barbero", peluqueria_id=peluqueria_id)
        if foto:
            barbero.foto = foto
            barbero.save()
        messages.success(request, "Barbero creado correctamente.")
        return redirect("sena:admin_peluqueros")
    return render(request, "administrador/admin_formulario_peluquero.html", {"peluquerias": Peluqueria.objects.all()})

@autorizacion(["Admin"])
def admin_editar_peluquero(request, id):
    peluquero = get_object_or_404(Usuario, id=id, rol="Barbero")
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero, "error": "Ese correo no tiene un formato válido.", "peluquerias": Peluqueria.objects.all()})
        if Usuario.objects.exclude(id=id).filter(email=email).exists():
            return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero, "error": "Ese correo ya está registrado.", "peluquerias": Peluqueria.objects.all()})
        error_telefono = validar_telefono(request.POST.get("telefono", peluquero.telefono).strip())
        foto = request.FILES.get("foto")
        error_imagen = validar_imagen(foto)
        if error_telefono or error_imagen:
            return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero, "error": error_telefono or error_imagen, "peluquerias": Peluqueria.objects.all()})
        peluquero.nombre = request.POST.get("nombre", "").strip()
        peluquero.apellido = request.POST.get("apellido", "").strip()
        peluquero.email = email
        peluquero.telefono = request.POST.get("telefono", "").strip()
        peluqueria_id = _id_entero(request.POST.get("peluqueria"))
        if peluqueria_id and Peluqueria.objects.filter(id=peluqueria_id).exists():
            peluquero.peluqueria_id = peluqueria_id
        if foto:
            peluquero.foto = foto
        elif request.POST.get("quitar_foto") and peluquero.foto:
            # El Admin puede quitar la foto actual desde el formulario.
            _borrar_archivo(peluquero.foto)
            peluquero.foto = None
        # La contraseña solo puede cambiarla el propio usuario desde su cuenta
        # o mediante recuperación. El administrador no puede modificarla.
        peluquero.save()
        messages.success(request, "Datos del barbero actualizados.")
        return redirect("sena:admin_peluqueros")
    return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero, "peluquerias": Peluqueria.objects.all()})

@autorizacion(["Admin"])
def admin_eliminar_peluquero(request, id):
    if request.method == "POST":
        barbero = Usuario.objects.filter(id=id, rol="Barbero").first()
        if barbero:
            estaba_activo = barbero.activo
            barbero.activo = False
            barbero.save(update_fields=["activo"])
            if estaba_activo:
                notificar_suspension_barbero(request, barbero)
            messages.success(request, "El barbero fue suspendido y sus citas futuras quedaron disponibles para reagendar.")
    return redirect("sena:admin_peluqueros")

@autorizacion(["Admin"])
def admin_reservas(request):
    reservas = Reserva.objects.select_related("cliente", "peluquero", "peluqueria").order_by("fecha", "hora")
    fecha = request.GET.get("fecha", "").strip()
    estado = request.GET.get("estado", "").strip()
    if fecha:
        reservas = reservas.filter(fecha=fecha)
    if estado in {opcion[0] for opcion in Reserva.ESTADOS}:
        reservas = reservas.filter(estado=estado)
    return render(request, "administrador/admin_listar_reservas.html", {"datos": reservas, "filtro_fecha": fecha, "filtro_estado": estado, "reserva_estados": Reserva.ESTADOS})


@autorizacion(["Admin"])
def admin_pedidos(request):
    """Muestra los pedidos para gestionar preparación, pago y entrega en tienda."""
    pedidos = (
        Pedido.objects.select_related("cliente")
        .prefetch_related("productos__producto")
        .order_by("-fecha")[:200]
    )
    return render(
        request,
        "administrador/admin_pedidos.html",
        {
            "pedidos": pedidos,
            "estados_pedido": tuple(
                estado for estado in Pedido.ESTADOS if estado[0] != "Completado"
            ),
        },
    )


@autorizacion(["Admin"])
def admin_actualizar_pedido(request, id):
    """Actualiza el estado logístico y el pago de un pedido desde el panel."""
    if request.method != "POST":
        return redirect("sena:admin_pedidos")

    pago_confirmado = request.POST.get("pago_confirmado") == "on"
    pedido, error = actualizar_pedido(
        id, request.POST.get("estado"), pago_confirmado
    )
    if error:
        if pedido and pedido.estado == "Completado":
            messages.info(request, error)
        else:
            messages.error(request, error)
        return redirect("sena:admin_pedidos")
    registrar_accion(
        request,
        "actualizar_pedido",
        "Pedido",
        pedido.id,
        f"Estado: {pedido.get_estado_display()}; pago confirmado: {pedido.pago_confirmado}",
    )

    Notificacion.objects.create(
        usuario=pedido.cliente,
        mensaje=(
            f"Tu pedido #{pedido.id} está: {pedido.get_estado_display()}. "
            + ("Pago confirmado en tienda." if pedido.pago_confirmado else "Pago pendiente en tienda.")
        ),
    )
    enviar_correo(
        pedido.cliente,
        f"Actualización de tu pedido #{pedido.id}",
        (
            f"Hola {pedido.cliente.nombre},\n\n"
            f"Tu pedido #{pedido.id} ahora está: {pedido.get_estado_display()}.\n"
            + ("El pago fue confirmado en tienda." if pedido.pago_confirmado else "El pago se realizará en tienda al recogerlo.")
        ),
        request=request,
        enlace=request.build_absolute_uri(reverse("sena:usuario_perfil")),
        texto_enlace="Ver mis pedidos",
    )
    messages.success(request, f"Pedido #{pedido.id} actualizado correctamente.")
    return redirect("sena:admin_pedidos")

@autorizacion(["Admin"])
def admin_crear_reserva(request):
    if request.method == "POST":
        # Los ids se validan como enteros para evitar errores con valores no numéricos
        cliente_id = _id_entero(request.POST.get("cliente"))
        peluquero_id = _id_entero(request.POST.get("peluquero"))
        peluqueria_id = _id_entero(request.POST.get("peluqueria"))
        cliente = Usuario.objects.filter(id=cliente_id, rol="Cliente").first() if cliente_id else None
        peluquero = Usuario.objects.filter(id=peluquero_id, rol="Barbero", activo=True).first() if peluquero_id else None
        peluqueria = Peluqueria.objects.filter(id=peluqueria_id).first() if peluqueria_id else None
        servicio = request.POST.get("servicio", "")
        if cliente is None or peluquero is None or peluqueria is None or servicio not in {item["nombre"] for item in catalogo_servicios()}:
            return render(request, "administrador/admin_formulario_reserva.html", {
                "error": "Completa todos los datos de la cita.",
                "clientes": Usuario.objects.filter(rol="Cliente"),
                "peluqueros": barberos_disponibles(),
                "peluquerias": Peluqueria.objects.all(),
                "servicios": catalogo_servicios(),
                "reserva_estados": Reserva.ESTADOS,
            })
        disponible, mensaje = cita_disponible(request.POST.get("fecha"), request.POST.get("hora"), peluqueria_id, servicio)
        if disponible:
            disponible, mensaje = barbero_esta_disponible(peluquero.id, request.POST.get("fecha"), request.POST.get("hora"), request.POST.get("servicio"))
        if not disponible:
            return render(request, "administrador/admin_formulario_reserva.html", {"error": mensaje, "clientes": Usuario.objects.filter(rol="Cliente"), "peluqueros": barberos_disponibles(), "peluquerias": Peluqueria.objects.all(), "servicios": catalogo_servicios(), "reserva_estados": Reserva.ESTADOS})
        reserva = Reserva.objects.create(
            cliente=cliente,
            peluquero=peluquero,
            peluqueria=peluqueria,
            fecha=request.POST.get("fecha"),
            hora=request.POST.get("hora"),
            servicio=servicio,
            estado=request.POST.get("estado", "Pendiente")
        )
        registrar_accion(request, "crear_cita", "Reserva", reserva.id, f"Cita de {reserva.servicio} para {reserva.cliente.email}")
        Notificacion.objects.create(usuario=cliente, reserva=reserva, mensaje=f"El administrador agendó tu cita de {reserva.servicio} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.")
        Notificacion.objects.create(usuario=peluquero, reserva=reserva, mensaje=f"El administrador agendó una cita de {reserva.servicio} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.")
        enviar_correo_cita(request, cliente, "Cita agendada en TecnoCorte", f"El administrador agendó tu cita de {reserva.servicio} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.", request.build_absolute_uri(reverse("sena:usuario_editar_reserva", args=[reserva.id])))
        enviar_correo_cita(request, peluquero, "Nueva cita agendada en TecnoCorte", f"Tienes una nueva cita con {cliente.nombre} {cliente.apellido} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.", request.build_absolute_uri(reverse("sena:peluquero_dashboard")))
        messages.success(request, "La cita fue creada y ambas partes recibieron una notificación.")
        _invalidar_cache_disponibilidad()
        return redirect("sena:admin_reservas")
    clientes = Usuario.objects.filter(rol="Cliente")
    peluqueros = barberos_disponibles()
    peluquerias = Peluqueria.objects.all()
    return render(request, "administrador/admin_formulario_reserva.html", {
        "clientes": clientes,
        "peluqueros": peluqueros,
        "peluquerias": peluquerias,
        "servicios": catalogo_servicios(),
        "reserva_estados": Reserva.ESTADOS
    })

@autorizacion(["Admin"])
def admin_editar_reserva(request, id):
    reserva = get_object_or_404(Reserva, id=id)
    if request.method == "POST":
        # Los ids se validan como enteros para evitar errores con valores no numéricos
        cliente_id = _id_entero(request.POST.get("cliente"))
        peluquero_id = _id_entero(request.POST.get("peluquero"))
        peluqueria_id = _id_entero(request.POST.get("peluqueria"))
        cliente = Usuario.objects.filter(id=cliente_id, rol="Cliente").first() if cliente_id else None
        peluquero = Usuario.objects.filter(id=peluquero_id, rol="Barbero", activo=True).first() if peluquero_id else None
        peluqueria = Peluqueria.objects.filter(id=peluqueria_id).first() if peluqueria_id else None
        servicio = request.POST.get("servicio", "").strip()
        if cliente is None or peluquero is None or peluqueria is None or servicio not in {item["nombre"] for item in catalogo_servicios()}:
            return redirect("sena:admin_editar_reserva", id=id)
        estado_anterior = reserva.estado
        estado_nuevo = request.POST.get("estado")
        if not transicion_valida(TRANSICIONES_RESERVA, estado_anterior, estado_nuevo):
            messages.error(request, f"No se puede pasar una cita de {estado_anterior} a {estado_nuevo}.")
            return redirect("sena:admin_editar_reserva", id=id)
        reserva.cliente = cliente
        reserva.peluquero = peluquero
        reserva.peluqueria = peluqueria
        reserva.fecha = request.POST.get("fecha")
        reserva.hora = request.POST.get("hora")
        reserva.servicio = servicio
        reserva.estado = estado_nuevo
        # Al cambiar la agenda se reinicia el aviso automático de la cita.
        reserva.recordatorio_correo_enviado = None
        disponible, mensaje = cita_disponible(request.POST.get("fecha"), request.POST.get("hora"), peluqueria_id, servicio)
        if disponible:
            disponible, mensaje = barbero_esta_disponible(peluquero.id, request.POST.get("fecha"), request.POST.get("hora"), request.POST.get("servicio"), reserva)
        if not disponible:
            return render(request, "administrador/admin_formulario_reserva.html", {"datos": reserva, "error": mensaje, "clientes": Usuario.objects.filter(rol="Cliente"), "peluqueros": barberos_disponibles(), "peluquerias": Peluqueria.objects.all(), "servicios": catalogo_servicios(), "reserva_estados": Reserva.ESTADOS})
        reserva.save()
        registrar_accion(request, "actualizar_cita", "Reserva", reserva.id, f"Estado: {estado_anterior} → {estado_nuevo}")
        Notificacion.objects.create(usuario=reserva.cliente, reserva=reserva, mensaje=f"Tu cita fue actualizada por el administrador para el {formato_cita(reserva)}.")
        Notificacion.objects.create(usuario=reserva.peluquero, reserva=reserva, mensaje=f"La cita de {reserva.cliente.nombre} fue actualizada para el {formato_cita(reserva)}.")
        if reserva.estado == "Cancelada":
            enviar_correo_cita(request, reserva.cliente, "Cita cancelada en TecnoCorte", f"Tu cita de {reserva.servicio} del {formato_cita(reserva)} fue cancelada por el administrador.")
        else:
            enviar_correo_cita(request, reserva.cliente, "Tu cita fue modificada en TecnoCorte", f"Tu cita de {reserva.servicio} fue modificada para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.", request.build_absolute_uri(reverse("sena:usuario_editar_reserva", args=[reserva.id])))
        if reserva.estado == "Cancelada":
            enviar_correo_cita(request, reserva.peluquero, "Cita cancelada en TecnoCorte", f"La cita de {reserva.cliente.nombre} del {formato_cita(reserva)} fue cancelada por el administrador.")
        else:
            enviar_correo_cita(request, reserva.peluquero, "Cita modificada en TecnoCorte", f"La cita de {reserva.cliente.nombre} fue modificada para el {formato_cita(reserva)}.", request.build_absolute_uri(reverse("sena:peluquero_dashboard")))
        messages.success(request, "La cita fue actualizada y se notificó a cliente y barbero.")
        _invalidar_cache_disponibilidad()
        return redirect("sena:admin_reservas")
    clientes = Usuario.objects.filter(rol="Cliente")
    peluqueros = barberos_disponibles()
    peluquerias = Peluqueria.objects.all()
    return render(request, "administrador/admin_formulario_reserva.html", {
        "datos": reserva,
        "clientes": clientes,
        "peluqueros": peluqueros,
        "peluquerias": peluquerias,
        "servicios": catalogo_servicios(),
        "reserva_estados": Reserva.ESTADOS
    })

@autorizacion(["Admin"])
def admin_eliminar_reserva(request, id):
    if request.method == "POST":
        reserva = Reserva.objects.select_related("cliente", "peluquero").filter(id=id).first()
        if reserva and reserva.estado != "Cancelada":
            # Las reservas son historial comercial: se cancelan, nunca se
            # eliminan, para conservar auditoría, calificaciones y avisos.
            reserva.estado = "Cancelada"
            reserva.save(update_fields=["estado"])
            Notificacion.objects.create(usuario=reserva.cliente, reserva=reserva, mensaje=f"Tu reserva #{reserva.id} del {formato_cita(reserva)} fue cancelada por el administrador.")
            Notificacion.objects.create(usuario=reserva.peluquero, reserva=reserva, mensaje=f"La reserva #{reserva.id} del {formato_cita(reserva)} fue cancelada por el administrador.")
            enviar_correo_cita(request, reserva.cliente, "Reserva cancelada en TecnoCorte", f"Tu reserva #{reserva.id} del {formato_cita(reserva)} fue cancelada por el administrador.")
            enviar_correo_cita(request, reserva.peluquero, "Reserva cancelada en TecnoCorte", f"La reserva #{reserva.id} del {formato_cita(reserva)} fue cancelada por el administrador.")
            messages.info(request, "La reserva fue cancelada y conservada en el historial.")
        elif reserva:
            messages.info(request, "La reserva ya estaba cancelada y se conservó en el historial.")
    _invalidar_cache_disponibilidad()
    return redirect("sena:admin_reservas")

@autorizacion(["Admin"])
def admin_cancelar_reserva(request, id):
    if request.method == "POST":
        reserva = Reserva.objects.select_related("cliente", "peluquero").filter(id=id).first()
        if reserva and reserva.estado != "Cancelada":
            reserva.estado = "Cancelada"
            reserva.save(update_fields=["estado"])
            Notificacion.objects.create(usuario=reserva.cliente, reserva=reserva, mensaje=f"Tu cita de {reserva.servicio} del {formato_cita(reserva)} fue cancelada por el administrador.")
            Notificacion.objects.create(usuario=reserva.peluquero, reserva=reserva, mensaje=f"La cita de {reserva.cliente.nombre} del {formato_cita(reserva)} fue cancelada por el administrador.")
            enviar_correo_cita(request, reserva.cliente, "Cita cancelada en TecnoCorte", f"Tu cita de {reserva.servicio} del {formato_cita(reserva)} fue cancelada por el administrador.")
            enviar_correo_cita(request, reserva.peluquero, "Cita cancelada en TecnoCorte", f"La cita de {reserva.cliente.nombre} del {formato_cita(reserva)} fue cancelada por el administrador.")
            messages.success(request, "La cita fue cancelada y se notificó a cliente y barbero.")
    _invalidar_cache_disponibilidad()
    return redirect("sena:admin_reservas")

@autorizacion(["Admin"])
def admin_horarios(request):
    peluquerias = Peluqueria.objects.all()
    peluqueria_id_raw = request.GET.get("peluqueria") or request.POST.get("peluqueria_seleccionada") or (str(peluquerias.first().id) if peluquerias.exists() else None)
    # Se valida que el id sea numérico para evitar errores con valores inválidos
    peluqueria_id = _id_entero(peluqueria_id_raw)
    peluqueria_actual = Peluqueria.objects.filter(id=peluqueria_id).first() if peluqueria_id else None
    if peluqueria_actual:
        # Crea en una sola operación los días que falten, en vez de 7 get_or_create
        dias_existentes = set(
            HorarioTrabajo.objects.filter(peluqueria=peluqueria_actual).values_list("dia_semana", flat=True)
        )
        faltantes = [numero for numero in range(7) if numero not in dias_existentes]
        if faltantes:
            HorarioTrabajo.objects.bulk_create([
                HorarioTrabajo(
                    peluqueria=peluqueria_actual, dia_semana=numero,
                    activo=numero < 6, hora_inicio=time(9, 0), hora_fin=time(18, 0),
                )
                for numero in faltantes
            ])
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "guardar_horarios" and peluqueria_actual:
            horarios_actuales = {h.dia_semana: h for h in HorarioTrabajo.objects.filter(peluqueria=peluqueria_actual)}
            a_guardar = []
            for numero in range(7):
                horario = horarios_actuales.get(numero)
                if horario is None:
                    continue
                horario.activo = request.POST.get(f"activo_{numero}") == "on"
                inicio_str = request.POST.get(f"inicio_{numero}", "09:00")
                fin_str = request.POST.get(f"fin_{numero}", "18:00")
                try:
                    horario.hora_inicio = datetime.strptime(inicio_str, "%H:%M").time()
                except (ValueError, TypeError):
                    horario.hora_inicio = time(9, 0)
                try:
                    horario.hora_fin = datetime.strptime(fin_str, "%H:%M").time()
                except (ValueError, TypeError):
                    horario.hora_fin = time(18, 0)
                a_guardar.append(horario)
            if a_guardar:
                HorarioTrabajo.objects.bulk_update(a_guardar, ["activo", "hora_inicio", "hora_fin"])
            _invalidar_cache_disponibilidad()
            messages.success(request, "Los horarios fueron guardados correctamente.")
        elif accion == "crear_bloqueo":
            fecha = request.POST.get("fecha")
            hora = request.POST.get("hora") or None
            # Se validan los formatos de fecha y hora antes de guardar
            try:
                fecha_valida = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else None
            except (ValueError, TypeError):
                fecha_valida = None
            try:
                hora_valida = datetime.strptime(hora, "%H:%M").time() if hora else None
            except (ValueError, TypeError):
                hora_valida = None
            if fecha_valida and peluqueria_actual:
                BloqueoHorario.objects.create(fecha=fecha_valida, hora=hora_valida, motivo=request.POST.get("motivo", ""), peluqueria=peluqueria_actual)
                _invalidar_cache_disponibilidad()
                messages.success(request, "El bloqueo fue programado correctamente.")
            else:
                return render(request, "administrador/admin_horarios.html", {
                    "horarios": HorarioTrabajo.objects.filter(peluqueria=peluqueria_actual).order_by("dia_semana") if peluqueria_actual else [],
                    "bloqueos": BloqueoHorario.objects.filter(peluqueria=peluqueria_actual) if peluqueria_actual else BloqueoHorario.objects.none(),
                    "hoy": datetime.today().date(),
                    "peluquerias": peluquerias,
                    "peluqueria_actual": peluqueria_actual,
                    "error": "La fecha o la peluquería seleccionada no son válidas.",
                })
        return redirect(f"{reverse('sena:admin_horarios')}?peluqueria={peluqueria_id or ''}")
    horarios = HorarioTrabajo.objects.filter(peluqueria=peluqueria_actual).order_by("dia_semana") if peluqueria_actual else []
    bloqueos = BloqueoHorario.objects.filter(peluqueria=peluqueria_actual) if peluqueria_actual else BloqueoHorario.objects.none()
    return render(request, "administrador/admin_horarios.html", {"horarios": horarios, "bloqueos": bloqueos, "hoy": datetime.today().date(), "peluquerias": peluquerias, "peluqueria_actual": peluqueria_actual})

@autorizacion(["Admin"])
def admin_eliminar_bloqueo(request, id):
    if request.method == "POST":
        BloqueoHorario.objects.filter(id=id).delete()
        _invalidar_cache_disponibilidad()
        messages.info(request, "El bloqueo fue eliminado.")
    return redirect("sena:admin_horarios")


@autorizacion(["Admin"])
def admin_peluquerias(request):
    return render(request, "administrador/admin_peluquerias.html", {"peluquerias": Peluqueria.objects.all()})


@autorizacion(["Admin"])
def admin_crear_peluqueria(request):
    if request.method == "POST":
        telefono = request.POST.get("telefono", "").strip()
        imagen = request.FILES.get("imagen")
        error_telefono = validar_telefono(telefono, obligatorio=True)
        error_imagen = validar_imagen(imagen)
        if error_telefono or error_imagen:
            barberos = Usuario.objects.filter(rol="Barbero").order_by("nombre", "apellido")
            return render(request, "administrador/admin_formulario_peluqueria.html", {"barberos": barberos, "error": error_telefono or error_imagen})
        peluqueria = Peluqueria.objects.create(
            nombre=request.POST.get("nombre"),
            ubicacion=request.POST.get("ubicacion"),
            telefono=telefono,
            descripcion=request.POST.get("descripcion", "").strip(),
        )
        if imagen:
            peluqueria.imagen = imagen
            peluqueria.save()
        dueno_id = request.POST.get("dueno") or None
        if dueno_id:
            dueno = Usuario.objects.filter(id=dueno_id, rol="Barbero").first()
            if dueno:
                peluqueria.dueno = dueno
                peluqueria.save()
        messages.success(request, "Barbería creada correctamente.")
        return redirect("sena:admin_peluquerias")
    barberos = Usuario.objects.filter(rol="Barbero").order_by("nombre", "apellido")
    return render(request, "administrador/admin_formulario_peluqueria.html", {"barberos": barberos})


@autorizacion(["Admin"])
def admin_editar_peluqueria(request, id):
    peluqueria = get_object_or_404(Peluqueria, id=id)
    if request.method == "POST":
        telefono = request.POST.get("telefono", peluqueria.telefono).strip()
        imagen = request.FILES.get("imagen")
        error_telefono = validar_telefono(telefono, obligatorio=True)
        error_imagen = validar_imagen(imagen)
        if error_telefono or error_imagen:
            barberos = Usuario.objects.filter(rol="Barbero").order_by("nombre", "apellido")
            return render(request, "administrador/admin_formulario_peluqueria.html", {"peluqueria": peluqueria, "barberos": barberos, "error": error_telefono or error_imagen})
        peluqueria.nombre = request.POST.get("nombre")
        peluqueria.ubicacion = request.POST.get("ubicacion")
        peluqueria.telefono = telefono
        peluqueria.descripcion = request.POST.get("descripcion", "").strip()
        if imagen:
            peluqueria.imagen = imagen
        dueno_id = request.POST.get("dueno") or None
        if dueno_id:
            dueno = Usuario.objects.filter(id=dueno_id, rol="Barbero").first()
            if dueno:
                peluqueria.dueno = dueno
                peluqueria.save()
        peluqueria.save()
        messages.success(request, "Barbería actualizada correctamente.")
        return redirect("sena:admin_peluquerias")
    barberos = Usuario.objects.filter(rol="Barbero").order_by("nombre", "apellido")
    return render(request, "administrador/admin_formulario_peluqueria.html", {"peluqueria": peluqueria, "barberos": barberos})


@autorizacion(["Admin"])
def admin_eliminar_peluqueria(request, id):
    if request.method == "POST":
        peluqueria = Peluqueria.objects.filter(id=id).first()
        if peluqueria and not Reserva.objects.filter(peluqueria=peluqueria).exists():
            peluqueria.delete()
            messages.success(request, "Barbería eliminada correctamente.")
        elif peluqueria:
            messages.error(request, "No puedes eliminar una barbería con reservas asociadas.")
    return redirect("sena:admin_peluquerias")


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


@autorizacion(["Admin"])
def admin_quitar_foto_peluqueria(request, id):
    """Quita la foto principal de una barbería que no cumple con las normas."""
    if request.method == "POST":
        peluqueria = get_object_or_404(Peluqueria, id=id)
        motivo = _motivo_eliminacion(request)
        if not motivo:
            messages.error(request, "Debes escribir el motivo por el que eliminas la foto.")
        elif peluqueria.imagen:
            _borrar_archivo(peluqueria.imagen)
            peluqueria.imagen = ""
            peluqueria.save(update_fields=["imagen"])
            avisar_foto_eliminada(peluqueria.dueno, f"la foto principal de «{peluqueria.nombre}»", motivo, request)
            messages.success(request, f"Foto principal de «{peluqueria.nombre}» eliminada.")
        else:
            messages.info(request, "Esa barbería no tiene foto principal.")
    return redirect("sena:admin_peluquerias")


@autorizacion(["Admin"])
def admin_galeria(request):
    """Listado de todas las fotos de galería para moderar su contenido."""
    fotos = ImagenPeluqueria.objects.select_related("peluqueria").order_by("-fecha")
    # Barberías que tienen al menos una foto: alimentan los botones de filtrado
    peluquerias = Peluqueria.objects.filter(galeria__isnull=False).distinct().order_by("nombre")
    return render(
        request,
        "administrador/admin_galeria.html",
        {"fotos": fotos, "peluquerias": peluquerias},
    )


@autorizacion(["Admin"])
def admin_eliminar_imagen_galeria(request, id):
    """Elimina una foto de galería de cualquier barbería."""
    if request.method == "POST":
        foto = get_object_or_404(ImagenPeluqueria, id=id)
        motivo = _motivo_eliminacion(request)
        if not motivo:
            messages.error(request, "Debes escribir el motivo por el que eliminas la foto.")
            return redirect("sena:admin_galeria")
        nombre = foto.peluqueria.nombre
        dueno = foto.peluqueria.dueno
        _borrar_archivo(foto.imagen)
        foto.delete()
        avisar_foto_eliminada(dueno, f"una foto de la galería de «{nombre}»", motivo, request)
        messages.success(request, f"Foto eliminada de la galería de «{nombre}».")
    return redirect("sena:admin_galeria")


@autorizacion(["Admin"])
def admin_productos(request):
    return render(request, "administrador/admin_productos.html", {"productos": Producto.objects.all().order_by("nombre")})


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


@autorizacion(["Admin"])
def admin_crear_producto(request):
    if request.method == "POST":
        error = datos_producto(request, Producto())
        if error:
            return render(request, "administrador/admin_formulario_producto.html", {"categorias": Producto.CATEGORIAS, "error": error})
        messages.success(request, "Producto creado correctamente.")
        return redirect("sena:admin_productos")
    return render(request, "administrador/admin_formulario_producto.html", {"categorias": Producto.CATEGORIAS})


@autorizacion(["Admin"])
def admin_editar_producto(request, id):
    producto = get_object_or_404(Producto, id=id)
    if request.method == "POST":
        error = datos_producto(request, producto)
        if error:
            return render(request, "administrador/admin_formulario_producto.html", {"producto": producto, "categorias": Producto.CATEGORIAS, "error": error})
        messages.success(request, "Producto actualizado correctamente.")
        return redirect("sena:admin_productos")
    return render(request, "administrador/admin_formulario_producto.html", {"producto": producto, "categorias": Producto.CATEGORIAS})


@autorizacion(["Admin"])
def admin_eliminar_producto(request, id):
    if request.method == "POST":
        Producto.objects.filter(id=id).update(stock=0, disponible=False)
        messages.info(request, "Producto retirado de la tienda.")
    return redirect("sena:admin_productos")


@autorizacion(["Admin"])
def admin_quitar_imagen_producto(request, id):
    """Quita la foto de un producto cuando el Admin considera que no cumple."""
    if request.method == "POST":
        producto = get_object_or_404(Producto, id=id)
        motivo = _motivo_eliminacion(request)
        if not motivo:
            messages.error(request, "Debes escribir el motivo por el que eliminas la foto.")
        elif producto.imagen:
            _borrar_archivo(producto.imagen)
            producto.imagen = ""
            producto.save(update_fields=["imagen"])
            messages.success(request, f"Foto de «{producto.nombre}» eliminada.")
        else:
            messages.info(request, "Ese producto no tiene foto.")
    return redirect("sena:admin_productos")


@autorizacion(["Admin"])
def admin_mensajes(request):
    mensajes = MensajeContacto.objects.all()
    MensajeContacto.objects.filter(leido=False).update(leido=True)
    return render(request, "administrador/admin_mensajes.html", {"mensajes": mensajes})


@autorizacion(["Admin"])
def admin_solicitudes_servicios(request):
    """El Admin revisa lo que los barberos piden y les crea el servicio o lo rechaza."""
    if request.method == "POST":
        solicitud = get_object_or_404(SolicitudServicio, id=_id_entero(request.POST.get("solicitud_id")))
        nota = request.POST.get("nota_admin", "").strip()[:300]
        if solicitud.estado != "pendiente":
            messages.info(request, "Esa solicitud ya fue resuelta.")
            return redirect("sena:admin_solicitudes_servicios")

        if request.POST.get("accion") == "aprobar":
            if Servicio.objects.filter(barbero=solicitud.barbero, nombre__iexact=solicitud.nombre).exists():
                messages.error(request, f"«{solicitud.nombre}» ya existe para {solicitud.barbero.nombre}.")
            else:
                Servicio.objects.create(
                    nombre=solicitud.nombre,
                    descripcion=solicitud.descripcion,
                    duracion=solicitud.duracion,
                    minutos=solicitud.minutos,
                    precio=solicitud.precio,
                    barbero=solicitud.barbero,
                    peluqueria=_peluqueria_del_barbero(solicitud.barbero_id),
                )
                solicitud.estado = "aprobada"
                solicitud.resuelta = timezone.now()
                solicitud.nota_admin = nota
                solicitud.save()
                Notificacion.objects.create(
                    usuario=solicitud.barbero,
                    mensaje=f"El administrador creó tu servicio «{solicitud.nombre}» por ${solicitud.precio} COP.",
                )
                messages.success(request, f"Servicio «{solicitud.nombre}» creado para {solicitud.barbero.nombre}.")

        elif request.POST.get("accion") == "rechazar":
            solicitud.estado = "rechazada"
            solicitud.resuelta = timezone.now()
            solicitud.nota_admin = nota
            solicitud.save()
            mensaje = f"El administrador rechazó tu solicitud del servicio «{solicitud.nombre}»."
            if nota:
                mensaje += f" Motivo: {nota}"
            Notificacion.objects.create(usuario=solicitud.barbero, mensaje=mensaje)
            messages.info(request, f"Solicitud de «{solicitud.nombre}» rechazada.")

        cache.delete("contador_solicitudes_servicio_admin")
        return redirect("sena:admin_solicitudes_servicios")

    contexto = {
        "pendientes": SolicitudServicio.objects.filter(estado="pendiente").select_related("barbero", "barbero__peluqueria"),
        "resueltas": SolicitudServicio.objects.exclude(estado="pendiente").select_related("barbero")[:30],
        "servicios_barberos": Servicio.objects.select_related("barbero", "peluqueria").order_by("barbero__nombre", "nombre"),
    }
    return render(request, "administrador/admin_solicitudes_servicios.html", contexto)


@autorizacion(["Admin"])
def admin_notificaciones(request):
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    notificaciones = Notificacion.objects.filter(usuario=usuario).order_by("-fecha")
    notificaciones.update(leida=True)
    return render(request, "administrador/admin_notificaciones.html", {"notificaciones": notificaciones})

@autorizacion(["Admin"])
def admin_perfil(request):
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    if request.method == "POST":
        usuario.nombre = request.POST.get("nombre", usuario.nombre)
        usuario.apellido = request.POST.get("apellido", usuario.apellido)
        telefono = request.POST.get("telefono", usuario.telefono).strip()
        error_telefono = validar_telefono(telefono)
        if error_telefono:
            messages.error(request, error_telefono)
            return redirect("sena:admin_perfil")
        foto = request.FILES.get("foto")
        error_imagen = validar_imagen(foto)
        if error_imagen:
            messages.error(request, error_imagen)
            return redirect("sena:admin_perfil")
        usuario.telefono = telefono
        if foto:
            usuario.foto = foto
        usuario.save()
        enviar_correo(
            usuario,
            "Tu perfil de administrador fue actualizado",
            f"Hola {usuario.nombre},\n\nTus datos de administrador fueron actualizados correctamente en TecnoCorte.",
            request=request,
            enlace=request.build_absolute_uri(reverse("sena:admin_perfil")),
            texto_enlace="Revisar mi perfil",
        )
        messages.success(request, "Perfil de administrador actualizado.")
        return redirect("sena:admin_perfil")
    contexto = contexto_carrito(request)
    contexto["usuario"] = usuario
    contexto["citas"] = Reserva.objects.none()
    contexto["pedidos"] = Pedido.objects.none()
    contexto["calificaciones_reservas"] = set()
    contexto["notificaciones"] = Notificacion.objects.filter(usuario=usuario).order_by("-fecha")
    return render(request, "administrador/admin_perfil.html", contexto)

@autorizacion(["Admin"])
def admin_ingresos(request):
    rol = request.GET.get("rol", "")
    ingresos = RegistroIngreso.objects.select_related("usuario").order_by("-fecha")
    if rol:
        ingresos = ingresos.filter(rol=rol)
    contexto = {
        "ingresos": ingresos,
        "rol_filtro": rol,
    }
    return render(request, "administrador/admin_listar_ingresos.html", contexto)


@autorizacion(["Admin"])
def admin_acciones(request):
    """Consulta de auditoría de acciones sensibles, solo visible para Admin."""
    from ..models import RegistroAccion

    acciones = RegistroAccion.objects.select_related("actor").all()[:300]
    return render(request, "administrador/admin_acciones.html", {"acciones": acciones})

@autorizacion(["Admin"])
def admin_errores(request):
    """Fallos registrados del sitio, para que el Admin los vea y los revise."""
    from ..models import RegistroError

    if request.method == "POST":
        estados = dict(RegistroError.ESTADOS)
        if request.POST.get("accion") == "revisar_todos":
            revisados = RegistroError.objects.filter(estado="pendiente").update(estado="revisado")
            if revisados:
                messages.success(request, f"Se marcaron {revisados} errores como revisados.")
        else:
            estado = request.POST.get("estado")
            if estado in estados:
                actualizados = RegistroError.objects.filter(
                    id=request.POST.get("registro_id")
                ).update(estado=estado)
                if actualizados:
                    messages.success(request, f"El error quedó como {estados[estado].lower()}.")
        # El contador del panel está en caché: se limpia para que el aviso baje ya.
        cache.delete("contador_errores_pendientes_admin")
        return redirect("sena:admin_errores")

    errores = RegistroError.objects.select_related("usuario").order_by("-fecha")[:200]
    contexto = {
        "errores": errores,
        "total_errores": RegistroError.objects.count(),
        "errores_pendientes": RegistroError.objects.filter(estado="pendiente").count(),
    }
    return render(request, "administrador/admin_errores.html", contexto)

# ═══════════════════════════════════════════════════════════════════════════
# GESTIÓN DE USUARIOS - SOLO ADMIN
# ═══════════════════════════════════════════════════════════════════════════

@autorizacion(["Admin"])
def admin_usuarios(request):
    """Listar todos los usuarios del sistema"""
    usuarios = Usuario.objects.all().order_by("-fecha_creacion")
    # Un solo SELECT con agregaciones en lugar de cuatro COUNT separados
    resumen = Usuario.objects.aggregate(
        total=Count("id"),
        total_admin=Count("id", filter=Q(rol="Admin")),
        total_clientes=Count("id", filter=Q(rol="Cliente")),
        total_peluqueros=Count("id", filter=Q(rol="Barbero")),
    )
    contexto = {
        "usuarios": usuarios,
        "total_usuarios": resumen["total"],
        "total_admin": resumen["total_admin"],
        "total_clientes": resumen["total_clientes"],
        "total_peluqueros": resumen["total_peluqueros"],
    }
    return render(request, "administrador/admin_usuarios.html", contexto)

@autorizacion(["Admin"])
def admin_crear_usuario(request):
    """Crear nuevo usuario"""
    administra_roles = puede_gestionar_roles(request)
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        rol_solicitado = request.POST.get("rol", "Cliente")
        if not administra_roles and rol_solicitado != "Cliente":
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": "No tienes permiso para asignar ese rol. Solo el administrador principal puede hacerlo.",
                "roles": Usuario.ROLES,
                "peluquerias": Peluqueria.objects.all(),
                "puede_gestionar_roles": False,
            })
        rol = rol_solicitado if administra_roles else "Cliente"

        # Validaciones
        if not all([nombre, apellido, email, password, rol]) or rol not in dict(Usuario.ROLES):
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": "Todos los campos son obligatorios",
                "roles": Usuario.ROLES,
                "peluquerias": Peluqueria.objects.all(),
                "puede_gestionar_roles": administra_roles,
            })
        error_telefono = validar_telefono(telefono)
        if error_telefono:
            return render(request, "administrador/admin_formulario_usuario.html", {"error": error_telefono, "roles": Usuario.ROLES, "peluquerias": Peluqueria.objects.all(), "puede_gestionar_roles": administra_roles})

        try:
            validate_email(email)
        except ValidationError:
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": "Ese correo no tiene un formato válido",
                "roles": Usuario.ROLES,
                "peluquerias": Peluqueria.objects.all(),
                "puede_gestionar_roles": administra_roles,
            })

        error_password = validar_password(password)
        if error_password:
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": error_password,
                "roles": Usuario.ROLES,
                "peluquerias": Peluqueria.objects.all(),
                "puede_gestionar_roles": administra_roles,
            })

        if Usuario.objects.filter(email__iexact=email).exists():
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": f"Ya existe un usuario con el email {email}",
                "roles": Usuario.ROLES,
                "peluquerias": Peluqueria.objects.all(),
                "puede_gestionar_roles": administra_roles,
            })

        peluqueria_id = _id_entero(request.POST.get("peluqueria"))
        if rol == "Barbero" and not peluqueria_id:
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": "Para crear un barbero debes seleccionar la barbería a la que pertenece.",
                "roles": Usuario.ROLES,
                "peluquerias": Peluqueria.objects.all(),
            })
        foto = request.FILES.get("foto")
        error_imagen = validar_imagen(foto)
        if error_imagen:
            return render(request, "administrador/admin_formulario_usuario.html", {"error": error_imagen, "roles": Usuario.ROLES, "peluquerias": Peluqueria.objects.all(), "puede_gestionar_roles": administra_roles})
        # Crear usuario
        usuario = Usuario.objects.create(
            nombre=nombre,
            apellido=apellido,
            email=email,
            password=make_password(password),
            telefono=telefono,
            rol=rol,
            peluqueria_id=peluqueria_id if rol == "Barbero" else None,
        )
        if foto:
            usuario.foto = foto
            usuario.save()
        messages.success(request, "Usuario creado correctamente.")
        return redirect("sena:admin_usuarios")

    return render(request, "administrador/admin_formulario_usuario.html", {
        "roles": Usuario.ROLES,
        "peluquerias": Peluqueria.objects.all(),
        "puede_gestionar_roles": administra_roles,
    })

@autorizacion(["Admin"])
def admin_editar_usuario(request, id):
    """Editar usuario existente"""
    usuario = get_object_or_404(Usuario, id=id)
    administra_roles = puede_gestionar_roles(request)
    
    if request.method == "POST":
        email = request.POST.get("email", usuario.email).strip().lower()
        # El correo debe ser válido y no estar repetido en otro usuario
        try:
            validate_email(email)
        except ValidationError:
            return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": "Ese correo no tiene un formato válido.", "peluquerias": Peluqueria.objects.all()})
        if Usuario.objects.exclude(id=id).filter(email__iexact=email).exists():
            return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": "Ese correo ya está registrado por otro usuario.", "peluquerias": Peluqueria.objects.all()})
        usuario.nombre = request.POST.get("nombre", usuario.nombre).strip()
        usuario.apellido = request.POST.get("apellido", usuario.apellido).strip()
        usuario.email = email
        telefono = request.POST.get("telefono", usuario.telefono).strip()
        error_telefono = validar_telefono(telefono)
        if error_telefono:
            return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": error_telefono, "peluquerias": Peluqueria.objects.all()})
        usuario.telefono = telefono
        nuevo_rol = request.POST.get("rol", usuario.rol) if administra_roles else usuario.rol
        # La cuenta principal nunca puede perder su rol, ni siquiera por sí misma.
        if usuario.email.lower() == ADMIN_PRINCIPAL_EMAIL:
            nuevo_rol = "Admin"
        if nuevo_rol not in dict(Usuario.ROLES):
            return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": "El rol seleccionado no es válido.", "peluquerias": Peluqueria.objects.all(), "puede_gestionar_roles": administra_roles})
        usuario.rol = nuevo_rol
        peluqueria_id = _id_entero(request.POST.get("peluqueria"))
        if nuevo_rol == "Barbero":
            if not peluqueria_id or not Peluqueria.objects.filter(id=peluqueria_id).exists():
                return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": "Para un barbero debes seleccionar la barbería a la que pertenece.", "peluquerias": Peluqueria.objects.all(), "puede_gestionar_roles": administra_roles})
            usuario.peluqueria_id = peluqueria_id
        else:
            usuario.peluqueria = None
        foto = request.FILES.get("foto")
        error_imagen = validar_imagen(foto)
        if error_imagen:
            return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": error_imagen, "peluquerias": Peluqueria.objects.all(), "puede_gestionar_roles": administra_roles})
        if foto:
            usuario.foto = foto
        elif request.POST.get("quitar_foto") and usuario.foto:
            # El Admin puede quitar la foto actual desde el formulario.
            _borrar_archivo(usuario.foto)
            usuario.foto = None

        # La contraseña de una cuenta existente no se modifica desde el panel
        # administrativo, aunque llegue un campo password en el POST.
        usuario.save()
        messages.success(request, "Usuario actualizado correctamente.")
        return redirect("sena:admin_usuarios")
    
    return render(request, "administrador/admin_formulario_usuario.html", {
        "usuario": usuario,
        "roles": Usuario.ROLES,
        "editar": True,
        "peluquerias": Peluqueria.objects.all(),
        "puede_gestionar_roles": administra_roles,
    })

@autorizacion(["Admin"])
def admin_eliminar_usuario(request, id):
    if request.method == "POST":
        usuario = Usuario.objects.filter(id=id).exclude(id=request.session["logueado"]["id"]).first()
        if usuario and usuario.rol != "Admin":
            usuario.activo = False
            usuario.save(update_fields=["activo"])
            registrar_accion(request, "suspender_usuario", "Usuario", id, f"Usuario suspendido: {usuario.nombre} {usuario.apellido}")
            messages.success(request, f"El usuario {usuario.nombre} {usuario.apellido} fue suspendido. Se conservó todo su historial.")
        else:
            messages.error(request, "No puedes eliminar o suspender tu propia cuenta ni una cuenta de administrador.")
    return redirect("sena:admin_usuarios")

@autorizacion(["Admin"])
def admin_suspender_usuario(request, id):
    """Suspender o activar un usuario"""
    if request.method == "POST":
        usuario = Usuario.objects.filter(id=id).first()
        if usuario and usuario.rol != "Admin":
            estaba_activo = usuario.activo
            usuario.activo = not usuario.activo
            usuario.save()
            if usuario.rol == "Barbero" and estaba_activo and not usuario.activo:
                notificar_suspension_barbero(request, usuario)
            messages.success(request, f"Usuario {'reactivado' if usuario.activo else 'suspendido'} correctamente.")
    return redirect("sena:admin_usuarios")


@autorizacion(["Admin"])
def admin_quitar_foto_usuario(request, id):
    """Quita la foto de perfil de un usuario cuya imagen no cumple."""
    origen = request.POST.get("origen", "usuarios")
    destino = "sena:admin_peluqueros" if origen == "peluqueros" else "sena:admin_usuarios"
    if request.method == "POST":
        usuario = get_object_or_404(Usuario, id=id)
        motivo = _motivo_eliminacion(request)
        if not motivo:
            messages.error(request, "Debes escribir el motivo por el que eliminas la foto.")
        elif usuario.foto:
            _borrar_archivo(usuario.foto)
            usuario.foto = None
            usuario.save(update_fields=["foto"])
            avisar_foto_eliminada(usuario, "tu foto de perfil", motivo, request)
            messages.success(request, f"Foto de {usuario.nombre} {usuario.apellido} eliminada.")
        else:
            messages.info(request, "Ese usuario no tiene foto de perfil.")
    return redirect(destino)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN GENERAL DEL SITIO - SOLO ADMIN
# ═══════════════════════════════════════════════════════════════════════════

@autorizacion(["Admin"])
def admin_configuracion(request):
    """Permite al Admin ajustar privacidad, datos generales y mantenimiento."""
    config = Configuracion.cargar()
    if request.method == "POST":
        config.sitio_nombre = request.POST.get("sitio_nombre", config.sitio_nombre).strip() or "TecnoCorte"
        correo = request.POST.get("correo_contacto", config.correo_contacto).strip()
        # El correo de contacto debe tener un formato válido.
        try:
            validate_email(correo)
            config.correo_contacto = correo
        except ValidationError:
            messages.error(request, "El correo de contacto no tiene un formato válido.")
            return redirect("sena:admin_configuracion")
        config.texto_aviso = request.POST.get("texto_aviso", "").strip()
        config.registro_abierto = request.POST.get("registro_abierto") == "on"
        config.mostrar_telefonos = request.POST.get("mostrar_telefonos") == "on"
        config.mostrar_ubicaciones = request.POST.get("mostrar_ubicaciones") == "on"
        config.mostrar_galeria = request.POST.get("mostrar_galeria") == "on"
        config.mostrar_calificaciones = request.POST.get("mostrar_calificaciones") == "on"
        config.modo_mantenimiento = request.POST.get("modo_mantenimiento") == "on"
        config.mensaje_mantenimiento = request.POST.get("mensaje_mantenimiento", "").strip()
        config.save()
        messages.success(request, "Configuración guardada correctamente.")
        return redirect("sena:admin_configuracion")
    return render(request, "administrador/admin_configuracion.html", {"config": config})
