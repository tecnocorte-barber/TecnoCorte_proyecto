import json
import hmac

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.utils import timezone
from django.db import IntegrityError, models, transaction
from django.contrib.auth.hashers import check_password, make_password
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from django.core import signing
from django.core.signing import salted_hmac
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.cache import cache
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from datetime import datetime, time, timedelta
from .models import Usuario, Peluqueria, Producto, Reserva, Pedido, PedidoProducto, RegistroIngreso, Notificacion, HorarioTrabajo, BloqueoHorario, MensajeContacto, Calificacion
from .utilidades import autorizacion, validar_password
from .context_processors import carrito_visible, guardar_carrito_activo, cargar_carrito_usuario

SERVICIOS = [
    {"nombre": "Corte de Cabello", "descripcion": "Lavado, corte preciso con tijera y máquina, peinado con productos premium.", "duracion": "45 Minutos", "minutos": 45, "precio": 40000},
    {"nombre": "Arreglo de Barba", "descripcion": "Toalla caliente, perfilado exacto, hidratación con aceites esenciales.", "duracion": "30 Minutos", "minutos": 30, "precio": 30000},
    {"nombre": "Combo Completo", "descripcion": "Corte de cabello + arreglo de barba + limpieza facial.", "duracion": "1 Hora 15 Min", "minutos": 75, "precio": 60000},
]

def _horarios_para_template(peluqueria_id=None):
    horarios = {}
    for h in HorarioTrabajo.objects.all():
        pid = str(h.peluqueria_id)
        if pid not in horarios:
            horarios[pid] = {}
        horarios[pid][h.dia_semana] = {"activo": h.activo, "inicio": h.hora_inicio.strftime("%H:%M"), "fin": h.hora_fin.strftime("%H:%M")}
    bloqueos = []
    qs = BloqueoHorario.objects.all()
    if peluqueria_id:
        qs = qs.filter(peluqueria_id=peluqueria_id)
    for b in qs:
        bloqueos.append({"fecha": b.fecha.strftime("%Y-%m-%d"), "hora": b.hora.strftime("%H:%M") if b.hora else None})
    ahora = timezone.localtime()
    return {
        "horarios_json": json.dumps(horarios),
        "bloqueos_json": json.dumps(bloqueos),
        "fecha_hoy": ahora.date().isoformat(),
        "hora_actual": ahora.strftime("%H:%M"),
    }


def _reservas_para_template():
    reservas = []
    for reserva in Reserva.objects.exclude(estado="Cancelada").only("peluquero_id", "fecha", "hora", "servicio"):
        reservas.append({
            "barbero": reserva.peluquero_id,
            "fecha": reserva.fecha.isoformat(),
            "hora": reserva.hora.strftime("%H:%M"),
            "minutos": minutos_servicio(reserva.servicio),
        })
    return {"reservas_json": json.dumps(reservas)}


def _id_entero(valor):
    try:
        valor = str(valor or "").strip()
        return int(valor) if valor.isdigit() else None
    except (TypeError, ValueError):
        return None

def contexto_carrito(request):
    carrito = request.session.get("carrito", {}) if carrito_visible(request) else {}
    items = []
    total = 0
    cantidad = 0
    for producto_id, cantidad_item in carrito.items():
        try:
            producto = Producto.objects.get(id=producto_id)
        except Producto.DoesNotExist:
            continue
        subtotal = producto.precio * int(cantidad_item)
        total += subtotal
        cantidad += int(cantidad_item)
        items.append({
            "producto": producto,
            "cantidad": int(cantidad_item),
            "subtotal": subtotal,
        })
    return {
        "items": items,
        "total": total,
        "cantidad": cantidad,
        "carrito": carrito,
        "mensaje_tienda": request.session.pop("mensaje_tienda", ""),
        "mensaje_carrito": request.session.pop("mensaje_carrito", ""),
    }

def registrar_ingreso(request, usuario):
    ip = request.META.get("REMOTE_ADDR", "")
    RegistroIngreso.objects.create(usuario=usuario, rol=usuario.rol, ip=ip)


def cita_disponible(fecha_texto, hora_texto, peluqueria_id=None, servicio=None):
    """Revisa el horario de trabajo y los bloqueos antes de crear una cita."""
    try:
        fecha = datetime.strptime(fecha_texto, "%Y-%m-%d").date()
        hora = datetime.strptime(hora_texto, "%H:%M").time()
    except (TypeError, ValueError):
        return False, "La fecha o la hora no son válidas."
    if fecha < timezone.localdate():
        return False, "No puedes reservar una fecha pasada."
    ahora = timezone.localtime()
    if fecha == ahora.date() and hora <= ahora.time().replace(second=0, microsecond=0):
        return False, "No puedes reservar una hora que ya pasó. Elige una hora posterior a la actual."

    horarios = HorarioTrabajo.objects.filter(dia_semana=fecha.weekday())
    if peluqueria_id:
        horarios = horarios.filter(peluqueria_id=peluqueria_id)
    horario = horarios.first()
    if horario is None:
        return False, "Esta barbería todavía no tiene horarios configurados."
    if not horario.activo:
        return False, "Ese día no se trabaja. Elige otra fecha."
    duracion = minutos_servicio(servicio)
    hora_fin_servicio = (datetime.combine(fecha, hora) + timedelta(minutes=duracion)).time()
    if hora < horario.hora_inicio or hora_fin_servicio > horario.hora_fin:
        return False, "La hora elegida está por fuera del horario de atención."
    bloqueos = BloqueoHorario.objects.filter(fecha=fecha)
    if peluqueria_id:
        bloqueos = bloqueos.filter(peluqueria_id=peluqueria_id)
    if bloqueos.filter(hora__isnull=True).exists():
        return False, "Ese día está bloqueado para citas."
    inicio_bloqueo = datetime.combine(fecha, hora)
    fin_bloqueo = inicio_bloqueo + timedelta(minutes=duracion)
    for bloqueo in bloqueos.exclude(hora__isnull=True):
        bloqueo_inicio = datetime.combine(fecha, bloqueo.hora)
        if inicio_bloqueo < bloqueo_inicio + timedelta(minutes=30) and fin_bloqueo > bloqueo_inicio:
            return False, "Ese horario está bloqueado. Elige otra hora."
    return True, ""


def minutos_servicio(servicio):
    for item in SERVICIOS:
        if item["nombre"] == servicio:
            return item["minutos"]
    return 30


def formato_cita(reserva):
    """Mantiene una fecha y hora legibles y consistentes en todos los avisos."""
    fecha = reserva.fecha if hasattr(reserva.fecha, "strftime") else datetime.strptime(str(reserva.fecha), "%Y-%m-%d").date()
    hora = reserva.hora if hasattr(reserva.hora, "strftime") else datetime.strptime(str(reserva.hora), "%H:%M").time()
    return f"{fecha.strftime('%d/%m/%Y')} a las {hora.strftime('%H:%M')}"


def enviar_correo(usuario, asunto, cuerpo):
    """Envía un correo sin romper la operación si el proveedor falla."""
    if not usuario or not usuario.email:
        return
    send_mail(
        asunto,
        cuerpo,
        settings.DEFAULT_FROM_EMAIL,
        [usuario.email],
        fail_silently=True,
    )


def enviar_correo_cita(request, usuario, asunto, cuerpo, enlace=None):
    if enlace:
        cuerpo = f"{cuerpo}\n\nPuedes revisar o modificar la cita aquí:\n{enlace}"
    enviar_correo(usuario, asunto, cuerpo)


RESET_SALT = "tecnocorte-password-reset"


def token_recuperacion(usuario):
    version = salted_hmac(RESET_SALT, usuario.password).hexdigest()
    return signing.dumps({"id": usuario.id, "version": version}, salt=RESET_SALT, compress=True)


def usuario_desde_token(token):
    try:
        datos = signing.loads(token, salt=RESET_SALT, max_age=3600)
    except (signing.BadSignature, signing.SignatureExpired, TypeError, ValueError):
        return None
    usuario = Usuario.objects.filter(id=datos.get("id"), activo=True).first()
    if not usuario:
        return None
    version_actual = salted_hmac(RESET_SALT, usuario.password).hexdigest()
    return usuario if hmac.compare_digest(datos.get("version", ""), version_actual) else None


def notificar_suspension_barbero(request, barbero):
    """Deja las citas futuras pendientes para que el cliente pueda reasignarlas."""
    ahora = timezone.localtime()
    reservas = Reserva.objects.select_related("cliente").filter(
        peluquero=barbero,
        fecha__gte=ahora.date(),
    ).exclude(estado__in=["Cancelada", "Completada"])
    for reserva in reservas:
        if reserva.fecha == ahora.date() and reserva.hora <= ahora.time().replace(second=0, microsecond=0):
            continue
        if reserva.estado != "Pendiente":
            reserva.estado = "Pendiente"
            reserva.save(update_fields=["estado"])
        momento = formato_cita(reserva)
        mensaje = (
            f"Tu barbero fue suspendido y no podrá atenderte el {momento}. "
            "Puedes reagendar la cita con otro barbero desde el enlace de modificación."
        )
        Notificacion.objects.create(usuario=reserva.cliente, reserva=reserva, mensaje=mensaje)
        enviar_correo_cita(
            request,
            reserva.cliente,
            "Necesitas reagendar tu cita en TecnoCorte",
            f"Hola {reserva.cliente.nombre},\n\n{mensaje}",
            request.build_absolute_uri(reverse("sena:usuario_editar_reserva", args=[reserva.id])),
        )


def barbero_esta_disponible(barbero_id, fecha_texto, hora_texto, servicio, reserva_actual=None):
    """Evita cruces de citas y reserva todo el tiempo que dura cada servicio."""
    try:
        inicio = datetime.combine(datetime.strptime(fecha_texto, "%Y-%m-%d").date(), datetime.strptime(hora_texto, "%H:%M").time())
    except (TypeError, ValueError):
        return False, "La fecha o la hora no son válidas."
    fin = inicio + timedelta(minutes=minutos_servicio(servicio))
    citas = Reserva.objects.filter(peluquero_id=barbero_id, fecha=fecha_texto).exclude(estado="Cancelada")
    if reserva_actual:
        citas = citas.exclude(id=reserva_actual.id)
    for cita in citas:
        inicio_existente = datetime.combine(cita.fecha, cita.hora)
        fin_existente = inicio_existente + timedelta(minutes=minutos_servicio(cita.servicio))
        if inicio < fin_existente and fin > inicio_existente:
            return False, "El barbero ya tiene una cita que ocupa ese horario."
    return True, ""

# INICIO - Sin login
def inicio(request):
    if request.session.get("logueado"):
        rol = request.session["logueado"]["rol"]
        if rol == "Admin":
            return redirect("sena:admin_reservas")
        elif rol == "Barbero":
            return redirect("sena:peluquero_dashboard")
    contexto = contexto_carrito(request)
    return render(request, "publicos/index.html", contexto)

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
            request.session["logueado"] = {
                "id": usuario.id,
                "nombre": usuario.nombre,
                "rol": usuario.rol
            }
            cargar_carrito_usuario(request, usuario.id)

            registrar_ingreso(request, usuario)
            messages.success(request, f"Bienvenido de nuevo, {usuario.nombre}.")

            # Si hay un "next" (página a la que quería ir), redirigir allá
            if proximo and url_has_allowed_host_and_scheme(proximo, {request.get_host()}, require_https=request.is_secure()):
                return redirect(proximo)

            if proximo == "carrito":
                return redirect("sena:carrito")

            if usuario.rol == "Admin":
                return redirect("sena:admin_reservas")
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

    return render(request, "publicos/login.html", {"proximo": request.GET.get("next", "")})


def solicitar_recuperacion(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
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
                f"Hola {usuario.nombre},\n\nRecibimos una solicitud para cambiar la contraseña de tu cuenta. Este enlace será válido durante una hora:\n\n{enlace}\n\nSi no solicitaste este cambio, puedes ignorar este mensaje.",
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
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        email = request.POST.get("email", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        password = request.POST.get("password", "")
        proximo = request.POST.get("next", "")

        if not nombre or not apellido or not email or not password:
            return render(request, "publicos/registro.html", {"error": "Completa todos los campos obligatorios."})

        # El correo debe tener un formato válido
        try:
            validate_email(email)
        except ValidationError:
            return render(request, "publicos/registro.html", {"error": "Ese correo no tiene un formato válido."})

        # La contraseña debe cumplir las reglas de seguridad
        error_password = validar_password(password)
        if error_password:
            return render(request, "publicos/registro.html", {"error": error_password})

        if Usuario.objects.filter(email=email).exists():
            return render(request, "publicos/registro.html", {"error": "Ya existe una cuenta con ese correo."})

        usuario = Usuario.objects.create(
            nombre=nombre,
            apellido=apellido,
            email=email,
            telefono=telefono,
            password=make_password(password),
            rol="Cliente"
        )
        for admin in Usuario.objects.filter(rol="Admin", activo=True):
            Notificacion.objects.create(usuario=admin, mensaje=f"Nuevo cliente registrado: {usuario.nombre} {usuario.apellido}.")
        enviar_correo(
            usuario,
            "Bienvenido a TecnoCorte",
            f"Hola {usuario.nombre},\n\nTu cuenta de TecnoCorte fue creada correctamente. Ya puedes reservar citas y comprar productos.\n\nIngresa a tu cuenta aquí:\n{request.build_absolute_uri(reverse('sena:usuario_perfil'))}",
        )
        guardar_carrito_activo(request)
        request.session["logueado"] = {
            "id": usuario.id,
            "nombre": usuario.nombre,
            "rol": usuario.rol
        }
        cargar_carrito_usuario(request, usuario.id)
        registrar_ingreso(request, usuario)
        messages.success(request, f"Cuenta creada. Bienvenido a TecnoCorte, {usuario.nombre}.")
        if proximo and url_has_allowed_host_and_scheme(proximo, {request.get_host()}, require_https=request.is_secure()):
            return redirect(proximo)
        if proximo == "carrito":
            return redirect("sena:carrito")
        return redirect("sena:inicio")

    return render(request, "publicos/registro.html", {"proximo": request.GET.get("next", "")})
def como_funciona(request):
    return render(request, "publicos/como_funciona.html")

def sobre_nosotros(request):
    return render(request, "publicos/sobre_nosotros.html")

def ayuda(request):
    contexto = contexto_carrito(request)
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        email = request.POST.get("email", "").strip()
        asunto = request.POST.get("asunto", "").strip()
        mensaje = request.POST.get("mensaje", "").strip()
        if nombre and email and asunto and mensaje:
            MensajeContacto.objects.create(nombre=nombre, email=email, asunto=asunto, mensaje=mensaje)
            for admin in Usuario.objects.filter(rol="Admin", activo=True):
                Notificacion.objects.create(usuario=admin, mensaje=f"Nuevo mensaje de contacto: {asunto}.")
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

def agregar_carrito(request, producto_id):
    es_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
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
        Notificacion.objects.create(
            usuario_id=cliente_id,
            mensaje=f"Tu pedido #{pedido.id} fue recibido por un total de ${pedido.total:,} COP.",
        )
        messages.success(request, f"Pedido #{pedido.id} confirmado correctamente.")
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

def usuario_servicios(request):
    contexto = contexto_carrito(request)
    contexto["servicios"] = SERVICIOS
    return render(request, "usuarios/usuario_servicios.html", contexto)

def usuario_peluquerias(request):
    contexto = contexto_carrito(request)
    contexto["peluquerias"] = Peluqueria.objects.all()
    return render(request, "usuarios/usuario_peluquerias.html", contexto)

def usuario_reservar_cita(request):
    contexto = contexto_carrito(request)
    contexto["peluqueros"] = Usuario.objects.filter(rol="Barbero", activo=True)
    contexto["peluquerias"] = Peluqueria.objects.all()
    contexto["servicios"] = SERVICIOS
    servicio_inicial = request.GET.get("servicio", "").strip()
    contexto["servicio_inicial"] = servicio_inicial if servicio_inicial in {item["nombre"] for item in SERVICIOS} else ""
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
    datos_validos = peluquero is not None and peluqueria is not None and bool(fecha) and bool(hora) and servicio in {item["nombre"] for item in SERVICIOS}
    disponible = datos_validos
    mensaje = ""
    if not datos_validos:
        mensaje = "Faltan datos. Elige servicio, barbero, barbería, fecha y hora antes de continuar."
    if disponible:
        disponible, mensaje = cita_disponible(fecha, hora, peluqueria_id, servicio)
    if disponible:
        disponible, mensaje = barbero_esta_disponible(peluquero_id, fecha, hora, servicio)
    if not disponible:
        contexto = contexto_carrito(request)
        contexto.update({"error": mensaje, "peluqueros": Usuario.objects.filter(rol="Barbero", activo=True), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS})
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
    datos_validos = peluquero is not None and peluqueria is not None and bool(fecha) and bool(hora) and servicio in {item["nombre"] for item in SERVICIOS}
    disponible = datos_validos
    mensaje = ""
    if not datos_validos:
        disponible = False
        mensaje = "Faltan datos. Elige servicio, barbero, barbería, fecha y hora antes de confirmar."
    if disponible:
        disponible, mensaje = cita_disponible(fecha, hora, peluqueria_id, servicio)
    if disponible:
        disponible, mensaje = barbero_esta_disponible(peluquero_id, fecha, hora, servicio)
    if not disponible:
        contexto = contexto_carrito(request)
        contexto.update({"error": mensaje, "peluqueros": Usuario.objects.filter(rol="Barbero", activo=True), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS})
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
            contexto.update({"error": mensaje, "peluqueros": Usuario.objects.filter(rol="Barbero", activo=True), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS})
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
        mensaje=f"Nueva cita: {reserva.cliente.nombre} reservó {reserva.servicio} para el {formato_cita(reserva)}.",
    )
    Notificacion.objects.create(
        usuario_id=reserva.cliente_id,
        reserva=reserva,
        mensaje=f"Tu cita de {reserva.servicio} para el {formato_cita(reserva)} fue reservada correctamente.",
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
    messages.success(request, "Cita reservada correctamente. El barbero ya fue notificado.")
    return redirect("sena:inicio")

@autorizacion(["Cliente"])
def usuario_perfil(request):
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    if request.method == "POST":
        usuario.nombre = request.POST.get("nombre", usuario.nombre)
        usuario.apellido = request.POST.get("apellido", usuario.apellido)
        usuario.telefono = request.POST.get("telefono", usuario.telefono)
        usuario.save()
        messages.success(request, "Perfil actualizado correctamente.")
        return redirect("sena:usuario_perfil")
    citas = Reserva.objects.filter(cliente=usuario).order_by("-fecha", "-hora")
    pedidos = Pedido.objects.filter(cliente=usuario).order_by("-fecha")
    calificaciones_reservas = set(Calificacion.objects.filter(cliente=usuario).values_list("reserva_id", flat=True))
    contexto = contexto_carrito(request)
    contexto["usuario"] = usuario
    contexto["citas"] = citas
    contexto["pedidos"] = pedidos
    contexto["notificaciones"] = Notificacion.objects.filter(usuario=usuario).order_by("-fecha")
    contexto["calificaciones_reservas"] = calificaciones_reservas
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
        disponible = bool(barbero and peluqueria and servicio in {item["nombre"] for item in SERVICIOS})
        mensaje = "Los datos de la reserva no son válidos."
        if disponible:
            disponible, mensaje = cita_disponible(fecha, hora, peluqueria.id, servicio)
        if disponible and barbero:
            disponible, mensaje = barbero_esta_disponible(barbero.id, fecha, hora, servicio, reserva)
        if disponible:
            barbero_anterior = reserva.peluquero
            reserva.fecha, reserva.hora, reserva.servicio = fecha, hora, servicio
            reserva.peluquero, reserva.peluqueria = barbero, peluqueria
            reserva.estado = "Pendiente"
            reserva.save()
            Notificacion.objects.create(usuario=barbero, reserva=reserva, mensaje=f"Una cita fue modificada para el {formato_cita(reserva)}.")
            Notificacion.objects.create(usuario=reserva.cliente, reserva=reserva, mensaje=f"Tu cita fue modificada para el {formato_cita(reserva)} y quedó pendiente de confirmación.")
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
            messages.success(request, "La cita fue modificada correctamente.")
            return redirect("sena:usuario_perfil")
        return render(request, "usuarios/usuario_editar_reserva.html", {"reserva": reserva, "peluqueros": Usuario.objects.filter(rol="Barbero", activo=True), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS, "error": mensaje or "Datos inválidos."})
    return render(request, "usuarios/usuario_editar_reserva.html", {"reserva": reserva, "peluqueros": Usuario.objects.filter(rol="Barbero", activo=True), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS})

@autorizacion(["Cliente"])
def usuario_notificaciones(request):
    contexto = contexto_carrito(request)
    contexto["notificaciones"] = Notificacion.objects.filter(
        usuario_id=request.session["logueado"]["id"]
    ).order_by("-fecha")
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
    messages.success(request, "Cita confirmada. Te esperamos en TecnoCorte.")
    return redirect("sena:usuario_notificaciones")

@autorizacion(["Cliente"])
def usuario_calificar(request, reserva_id):
    if request.method != "POST":
        return redirect("sena:usuario_perfil")
    cliente_id = request.session["logueado"]["id"]
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
            return render(request, "usuarios/cambiar_password.html", {"rol": rol, "error": error})
        usuario.password = make_password(nueva)
        usuario.save(update_fields=["password"])
        messages.success(request, "Contraseña actualizada correctamente.")
        return redirect(destino)
    return render(request, "usuarios/cambiar_password.html", {"rol": rol})

# ═══════════════════════════════════════════════════════════════════════════
# PELUQUERO
# ═══════════════════════════════════════════════════════════════════════════

@autorizacion(["Barbero"])
def peluquero_dashboard(request):
    barbero_id = request.session["logueado"]["id"]
    citas = Reserva.objects.filter(peluquero_id=barbero_id).order_by("fecha", "hora")
    precios = {item["nombre"]: item["precio"] for item in SERVICIOS}
    citas_completadas = citas.filter(estado="Completada")
    citas_pendientes = citas.filter(estado="Pendiente")
    citas_canceladas = citas.filter(estado="Cancelada")
    citas_hoy = citas.filter(fecha=timezone.localdate())
    ingresos_hoy = sum(precios.get(c.servicio, 0) for c in citas_hoy.filter(estado="Completada"))
    ingresos_total = sum(precios.get(c.servicio, 0) for c in citas_completadas)
    califs = Calificacion.objects.filter(barbero_id=barbero_id)
    promedio = 0
    if califs.exists():
        promedio = round(califs.aggregate(models.Avg("puntuacion"))["puntuacion__avg"], 1)
    contexto = {
        "citas": citas,
        "citas_completadas": citas_completadas,
        "citas_pendientes": citas_pendientes,
        "citas_canceladas": citas_canceladas,
        "citas_hoy": citas_hoy,
        "ingresos_hoy": ingresos_hoy,
        "ingresos_total": ingresos_total,
        "total_citas": citas.count(),
        "promedio": promedio,
        "total_calificaciones": califs.count(),
        "calificaciones": califs[:5],
    }
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
        cita.estado = nuevo_estado
        cita.save()
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
            messages.success(request, f"Cita actualizada a {nuevo_estado.lower()}.")
    return redirect("sena:peluquero_dashboard")

@autorizacion(["Barbero"])
def peluquero_perfil(request):
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    if request.method == "POST":
        usuario.nombre = request.POST.get("nombre", usuario.nombre)
        usuario.apellido = request.POST.get("apellido", usuario.apellido)
        usuario.telefono = request.POST.get("telefono", usuario.telefono)
        usuario.save()
        messages.success(request, "Perfil actualizado correctamente.")
        return redirect("sena:peluquero_perfil")
    citas = Reserva.objects.filter(peluquero=usuario).order_by("-fecha", "-hora")
    calificaciones = Calificacion.objects.filter(barbero=usuario)
    promedio = 0
    if calificaciones.exists():
        promedio = round(calificaciones.aggregate(models.Avg("puntuacion"))["puntuacion__avg"], 1)
    contexto = {
        "usuario": usuario,
        "citas": citas,
        "calificaciones": calificaciones,
        "promedio": promedio,
        "total_calificaciones": calificaciones.count(),
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
                "servicios": SERVICIOS,
                "reserva_estados": Reserva.ESTADOS,
                "error": "Selecciona un cliente y una peluquería válidos.",
            })
        disponible, mensaje = cita_disponible(request.POST.get("fecha"), request.POST.get("hora"), peluqueria.id, request.POST.get("servicio"))
        if disponible:
            disponible, mensaje = barbero_esta_disponible(request.session["logueado"]["id"], request.POST.get("fecha"), request.POST.get("hora"), request.POST.get("servicio"))
        if not disponible:
            contexto = {"clientes": Usuario.objects.filter(rol="Cliente"), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS, "error": mensaje}
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
            mensaje=f"El barbero {request.session['logueado']['nombre']} agendó una cita de {reserva.servicio} para el {formato_cita(reserva)}. Confírmala desde tu cuenta.",
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
        "servicios": SERVICIOS,
        "reserva_estados": Reserva.ESTADOS,
    }
    return render(request, "peluqueros/peluquero_crear_cita.html", contexto)


@autorizacion(["Barbero"])
def peluquero_notificaciones(request):
    notificaciones = Notificacion.objects.filter(usuario_id=request.session["logueado"]["id"]).order_by("-fecha")
    notificaciones.update(leida=True)
    return render(request, "peluqueros/peluquero_notificaciones.html", {"notificaciones": notificaciones})

# ═══════════════════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════════════════

@autorizacion(["Admin"])
def admin_dashboard(request):
    reservas = Reserva.objects.all()
    ventas_servicios = sum(next((item["precio"] for item in SERVICIOS if item["nombre"] == reserva.servicio), 0) for reserva in reservas.filter(estado="Completada"))
    ventas_productos = sum(pedido.total for pedido in Pedido.objects.exclude(estado="Cancelado"))
    total = ventas_servicios + ventas_productos
    estados = {estado[0]: reservas.filter(estado=estado[0]).count() for estado in Reserva.ESTADOS}
    maximo = max(estados.values()) if any(estados.values()) else 1
    return render(request, "administrador/admin_dashboard.html", {"total": total, "ventas_servicios": ventas_servicios, "ventas_productos": ventas_productos, "total_reservas": reservas.count(), "total_clientes": Usuario.objects.filter(rol="Cliente").count(), "estados": estados, "maximo": maximo, "ultimas_reservas": reservas.select_related("cliente", "peluquero").order_by("-fecha", "-hora")[:6]})

@autorizacion(["Admin"])
def admin_peluqueros(request):
    peluqueros = Usuario.objects.filter(rol="Barbero")
    return render(request, "administrador/admin_listar_peluqueros.html", {"datos": peluqueros})

@autorizacion(["Admin"])
def admin_crear_peluquero(request):
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        if not all([nombre, apellido, email, password]):
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": "Completa todos los campos obligatorios."})
        try:
            validate_email(email)
        except ValidationError:
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": "Ese correo no tiene un formato válido."})
        error_password = validar_password(password)
        if error_password:
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": error_password})
        if Usuario.objects.filter(email=email).exists():
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": "Ya existe un usuario con ese correo."})
        Usuario.objects.create(nombre=nombre, apellido=apellido, email=email, password=make_password(password), telefono=request.POST.get("telefono", "").strip(), rol="Barbero")
        messages.success(request, "Barbero creado correctamente.")
        return redirect("sena:admin_peluqueros")
    return render(request, "administrador/admin_formulario_peluquero.html")

@autorizacion(["Admin"])
def admin_editar_peluquero(request, id):
    peluquero = get_object_or_404(Usuario, id=id, rol="Barbero")
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        try:
            validate_email(email)
        except ValidationError:
            return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero, "error": "Ese correo no tiene un formato válido."})
        if Usuario.objects.exclude(id=id).filter(email=email).exists():
            return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero, "error": "Ese correo ya está registrado."})
        peluquero.nombre = request.POST.get("nombre", "").strip()
        peluquero.apellido = request.POST.get("apellido", "").strip()
        peluquero.email = email
        peluquero.telefono = request.POST.get("telefono", "").strip()
        if request.POST.get("password"):
            # Solo se actualiza si la nueva contraseña cumple las reglas
            error_password = validar_password(request.POST.get("password"))
            if error_password:
                return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero, "error": error_password})
            peluquero.password = make_password(request.POST.get("password"))
        peluquero.save()
        messages.success(request, "Datos del barbero actualizados.")
        return redirect("sena:admin_peluqueros")
    return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero})

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
    return render(request, "administrador/admin_listar_reservas.html", {"datos": reservas})

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
        if cliente is None or peluquero is None or peluqueria is None or servicio not in {item["nombre"] for item in SERVICIOS}:
            return render(request, "administrador/admin_formulario_reserva.html", {
                "error": "Completa todos los datos de la cita.",
                "clientes": Usuario.objects.filter(rol="Cliente"),
                "peluqueros": Usuario.objects.filter(rol="Barbero", activo=True),
                "peluquerias": Peluqueria.objects.all(),
                "servicios": SERVICIOS,
                "reserva_estados": Reserva.ESTADOS,
            })
        disponible, mensaje = cita_disponible(request.POST.get("fecha"), request.POST.get("hora"), peluqueria_id, servicio)
        if disponible:
            disponible, mensaje = barbero_esta_disponible(peluquero.id, request.POST.get("fecha"), request.POST.get("hora"), request.POST.get("servicio"))
        if not disponible:
            return render(request, "administrador/admin_formulario_reserva.html", {"error": mensaje, "clientes": Usuario.objects.filter(rol="Cliente"), "peluqueros": Usuario.objects.filter(rol="Barbero", activo=True), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS, "reserva_estados": Reserva.ESTADOS})
        reserva = Reserva.objects.create(
            cliente=cliente,
            peluquero=peluquero,
            peluqueria=peluqueria,
            fecha=request.POST.get("fecha"),
            hora=request.POST.get("hora"),
            servicio=servicio,
            estado=request.POST.get("estado", "Pendiente")
        )
        Notificacion.objects.create(usuario=cliente, reserva=reserva, mensaje=f"El administrador agendó tu cita de {reserva.servicio} para el {formato_cita(reserva)}.")
        Notificacion.objects.create(usuario=peluquero, reserva=reserva, mensaje=f"El administrador agendó una cita de {reserva.servicio} para el {formato_cita(reserva)}.")
        enviar_correo_cita(request, cliente, "Cita agendada en TecnoCorte", f"El administrador agendó tu cita de {reserva.servicio} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.", request.build_absolute_uri(reverse("sena:usuario_editar_reserva", args=[reserva.id])))
        enviar_correo_cita(request, peluquero, "Nueva cita agendada en TecnoCorte", f"Tienes una nueva cita con {cliente.nombre} {cliente.apellido} para el {formato_cita(reserva)} en {reserva.peluqueria.nombre}.", request.build_absolute_uri(reverse("sena:peluquero_dashboard")))
        messages.success(request, "La cita fue creada y ambas partes recibieron una notificación.")
        return redirect("sena:admin_reservas")
    clientes = Usuario.objects.filter(rol="Cliente")
    peluqueros = Usuario.objects.filter(rol="Barbero", activo=True)
    peluquerias = Peluqueria.objects.all()
    return render(request, "administrador/admin_formulario_reserva.html", {
        "clientes": clientes,
        "peluqueros": peluqueros,
        "peluquerias": peluquerias,
        "servicios": SERVICIOS,
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
        if cliente is None or peluquero is None or peluqueria is None or servicio not in {item["nombre"] for item in SERVICIOS}:
            return redirect("sena:admin_editar_reserva", id=id)
        reserva.cliente = cliente
        reserva.peluquero = peluquero
        reserva.peluqueria = peluqueria
        reserva.fecha = request.POST.get("fecha")
        reserva.hora = request.POST.get("hora")
        reserva.servicio = servicio
        reserva.estado = request.POST.get("estado")
        disponible, mensaje = cita_disponible(request.POST.get("fecha"), request.POST.get("hora"), peluqueria_id, servicio)
        if disponible:
            disponible, mensaje = barbero_esta_disponible(peluquero.id, request.POST.get("fecha"), request.POST.get("hora"), request.POST.get("servicio"), reserva)
        if not disponible:
            return render(request, "administrador/admin_formulario_reserva.html", {"datos": reserva, "error": mensaje, "clientes": Usuario.objects.filter(rol="Cliente"), "peluqueros": Usuario.objects.filter(rol="Barbero", activo=True), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS, "reserva_estados": Reserva.ESTADOS})
        reserva.save()
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
        return redirect("sena:admin_reservas")
    clientes = Usuario.objects.filter(rol="Cliente")
    peluqueros = Usuario.objects.filter(rol="Barbero", activo=True)
    peluquerias = Peluqueria.objects.all()
    return render(request, "administrador/admin_formulario_reserva.html", {
        "datos": reserva,
        "clientes": clientes,
        "peluqueros": peluqueros,
        "peluquerias": peluquerias,
        "servicios": SERVICIOS,
        "reserva_estados": Reserva.ESTADOS
    })

@autorizacion(["Admin"])
def admin_eliminar_reserva(request, id):
    if request.method == "POST":
        reserva = Reserva.objects.select_related("cliente", "peluquero").filter(id=id).first()
        if reserva:
            Notificacion.objects.create(usuario=reserva.cliente, mensaje=f"La reserva #{reserva.id} fue eliminada por el administrador.")
            Notificacion.objects.create(usuario=reserva.peluquero, mensaje=f"La reserva #{reserva.id} fue eliminada por el administrador.")
            enviar_correo_cita(request, reserva.cliente, "Reserva eliminada en TecnoCorte", f"Tu reserva #{reserva.id} del {formato_cita(reserva)} fue eliminada por el administrador.")
            enviar_correo_cita(request, reserva.peluquero, "Reserva eliminada en TecnoCorte", f"La reserva #{reserva.id} del {formato_cita(reserva)} fue eliminada por el administrador.")
            reserva.delete()
            messages.info(request, "La reserva fue eliminada y se notificó a sus participantes.")
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
    return redirect("sena:admin_reservas")

@autorizacion(["Admin"])
def admin_horarios(request):
    peluquerias = Peluqueria.objects.all()
    peluqueria_id_raw = request.GET.get("peluqueria") or request.POST.get("peluqueria_seleccionada") or (str(peluquerias.first().id) if peluquerias.exists() else None)
    # Se valida que el id sea numérico para evitar errores con valores inválidos
    peluqueria_id = _id_entero(peluqueria_id_raw)
    peluqueria_actual = Peluqueria.objects.filter(id=peluqueria_id).first() if peluqueria_id else None
    if peluqueria_actual:
        for numero in range(7):
            HorarioTrabajo.objects.get_or_create(
                peluqueria=peluqueria_actual,
                dia_semana=numero,
                defaults={"activo": numero < 6, "hora_inicio": time(9, 0), "hora_fin": time(18, 0)},
            )
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "guardar_horarios" and peluqueria_actual:
            for numero in range(7):
                horario, _ = HorarioTrabajo.objects.get_or_create(
                    peluqueria=peluqueria_actual, dia_semana=numero,
                    defaults={"activo": numero < 6, "hora_inicio": time(9, 0), "hora_fin": time(18, 0)},
                )
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
                horario.save()
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
        messages.info(request, "El bloqueo fue eliminado.")
    return redirect("sena:admin_horarios")


@autorizacion(["Admin"])
def admin_peluquerias(request):
    return render(request, "administrador/admin_peluquerias.html", {"peluquerias": Peluqueria.objects.all()})


@autorizacion(["Admin"])
def admin_crear_peluqueria(request):
    if request.method == "POST":
        Peluqueria.objects.create(nombre=request.POST.get("nombre"), ubicacion=request.POST.get("ubicacion"), telefono=request.POST.get("telefono"))
        messages.success(request, "Barbería creada correctamente.")
        return redirect("sena:admin_peluquerias")
    return render(request, "administrador/admin_formulario_peluqueria.html")


@autorizacion(["Admin"])
def admin_editar_peluqueria(request, id):
    peluqueria = get_object_or_404(Peluqueria, id=id)
    if request.method == "POST":
        peluqueria.nombre = request.POST.get("nombre")
        peluqueria.ubicacion = request.POST.get("ubicacion")
        peluqueria.telefono = request.POST.get("telefono")
        peluqueria.save()
        messages.success(request, "Barbería actualizada correctamente.")
        return redirect("sena:admin_peluquerias")
    return render(request, "administrador/admin_formulario_peluqueria.html", {"peluqueria": peluqueria})


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


@autorizacion(["Admin"])
def admin_productos(request):
    return render(request, "administrador/admin_productos.html", {"productos": Producto.objects.all().order_by("nombre")})


def notificar_producto_agotado(producto):
    mensaje = f"Stock agotado: {producto.nombre}."
    for admin in Usuario.objects.filter(rol="Admin", activo=True):
        Notificacion.objects.create(usuario=admin, mensaje=mensaje)


def datos_producto(request, producto=None):
    stock_anterior = producto.stock if producto.pk else None
    producto.nombre = request.POST.get("nombre")
    producto.descripcion = request.POST.get("descripcion", "")
    # El precio se convierte a entero y nunca queda negativo
    try:
        producto.precio = max(0, int(request.POST.get("precio", 0)))
    except (TypeError, ValueError):
        producto.precio = 0
    producto.categoria = request.POST.get("categoria", "Herramientas")
    try:
        producto.stock = max(0, int(request.POST.get("stock", 0)))
    except (TypeError, ValueError):
        producto.stock = 0
    producto.disponible = request.POST.get("disponible") == "on" and producto.stock > 0
    producto.save()
    if stock_anterior and stock_anterior > 0 and producto.stock == 0:
        notificar_producto_agotado(producto)


@autorizacion(["Admin"])
def admin_crear_producto(request):
    if request.method == "POST":
        datos_producto(request, Producto())
        messages.success(request, "Producto creado correctamente.")
        return redirect("sena:admin_productos")
    return render(request, "administrador/admin_formulario_producto.html", {"categorias": Producto.CATEGORIAS})


@autorizacion(["Admin"])
def admin_editar_producto(request, id):
    producto = get_object_or_404(Producto, id=id)
    if request.method == "POST":
        datos_producto(request, producto)
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
def admin_mensajes(request):
    mensajes = MensajeContacto.objects.all()
    MensajeContacto.objects.filter(leido=False).update(leido=True)
    return render(request, "administrador/admin_mensajes.html", {"mensajes": mensajes})


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
        usuario.save()
        messages.success(request, "Perfil de administrador actualizado.")
        return redirect("sena:admin_perfil")
    contexto = contexto_carrito(request)
    contexto["usuario"] = usuario
    contexto["citas"] = Reserva.objects.none()
    contexto["pedidos"] = Pedido.objects.none()
    contexto["calificaciones_reservas"] = set()
    contexto["notificaciones"] = Notificacion.objects.filter(usuario=usuario).order_by("-fecha")
    return render(request, "usuarios/usuario_perfil.html", contexto)

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

# ═══════════════════════════════════════════════════════════════════════════
# GESTIÓN DE USUARIOS - SOLO ADMIN
# ═══════════════════════════════════════════════════════════════════════════

@autorizacion(["Admin"])
def admin_usuarios(request):
    """Listar todos los usuarios del sistema"""
    usuarios = Usuario.objects.all().order_by("-fecha_creacion")
    contexto = {
        "usuarios": usuarios,
        "total_usuarios": usuarios.count(),
        "total_admin": Usuario.objects.filter(rol="Admin").count(),
        "total_clientes": Usuario.objects.filter(rol="Cliente").count(),
        "total_peluqueros": Usuario.objects.filter(rol="Barbero").count(),
    }
    return render(request, "administrador/admin_usuarios.html", contexto)

@autorizacion(["Admin"])
def admin_crear_usuario(request):
    """Crear nuevo usuario"""
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        rol = request.POST.get("rol", "Cliente")

        # Validaciones
        if not all([nombre, apellido, email, password, rol]) or rol not in dict(Usuario.ROLES):
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": "Todos los campos son obligatorios"
            })

        try:
            validate_email(email)
        except ValidationError:
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": "Ese correo no tiene un formato válido"
            })

        error_password = validar_password(password)
        if error_password:
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": error_password
            })

        if Usuario.objects.filter(email=email).exists():
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": f"Ya existe un usuario con el email {email}"
            })

        # Crear usuario
        Usuario.objects.create(
            nombre=nombre,
            apellido=apellido,
            email=email,
            password=make_password(password),
            telefono=telefono,
            rol=rol
        )
        messages.success(request, "Usuario creado correctamente.")
        return redirect("sena:admin_usuarios")

    return render(request, "administrador/admin_formulario_usuario.html", {
        "roles": Usuario.ROLES
    })

@autorizacion(["Admin"])
def admin_editar_usuario(request, id):
    """Editar usuario existente"""
    usuario = get_object_or_404(Usuario, id=id)
    
    if request.method == "POST":
        email = request.POST.get("email", usuario.email).strip()
        # El correo debe ser válido y no estar repetido en otro usuario
        try:
            validate_email(email)
        except ValidationError:
            return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": "Ese correo no tiene un formato válido."})
        if Usuario.objects.exclude(id=id).filter(email=email).exists():
            return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": "Ese correo ya está registrado por otro usuario."})
        usuario.nombre = request.POST.get("nombre", usuario.nombre).strip()
        usuario.apellido = request.POST.get("apellido", usuario.apellido).strip()
        usuario.email = email
        usuario.telefono = request.POST.get("telefono", usuario.telefono).strip()
        nuevo_rol = request.POST.get("rol", usuario.rol)
        if nuevo_rol not in dict(Usuario.ROLES):
            return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": "El rol seleccionado no es válido."})
        usuario.rol = nuevo_rol
        
        # Actualizar contraseña si se proporciona y cumple las reglas
        password = request.POST.get("password", "").strip()
        if password:
            error_password = validar_password(password)
            if error_password:
                return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": error_password})
            usuario.password = make_password(password)
        
        usuario.save()
        messages.success(request, "Usuario actualizado correctamente.")
        return redirect("sena:admin_usuarios")
    
    return render(request, "administrador/admin_formulario_usuario.html", {
        "usuario": usuario,
        "roles": Usuario.ROLES,
        "editar": True
    })

@autorizacion(["Admin"])
def admin_eliminar_usuario(request, id):
    if request.method == "POST":
        usuario = Usuario.objects.filter(id=id).exclude(id=request.session["logueado"]["id"]).first()
        if usuario:
            estaba_activo = usuario.activo
            usuario.activo = False
            usuario.save(update_fields=["activo"])
            if usuario.rol == "Barbero" and estaba_activo:
                notificar_suspension_barbero(request, usuario)
            messages.info(request, "El usuario fue suspendido.")
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
