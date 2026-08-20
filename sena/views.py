import json

from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import JsonResponse
from django.utils import timezone
from django.db import IntegrityError, models, transaction
from datetime import datetime, time, timedelta
from .models import Usuario, Peluqueria, Producto, Reserva, Pedido, PedidoProducto, RegistroIngreso, Notificacion, HorarioTrabajo, BloqueoHorario, MensajeContacto, Calificacion
from .utilidades import autorizacion

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
    return {"horarios_json": json.dumps(horarios), "bloqueos_json": json.dumps(bloqueos)}


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
    carrito = request.session.get("carrito", {})
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
    if bloqueos.filter(hora=hora).exists():
        return False, "Ese horario está bloqueado. Elige otra hora."
    return True, ""


def minutos_servicio(servicio):
    for item in SERVICIOS:
        if item["nombre"] == servicio:
            return item["minutos"]
    return 30


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
        rol_seleccionado = request.POST.get("rol", "Cliente")
        proximo = request.POST.get("next", "")

        if rol_seleccionado == "Usuario":
            rol_seleccionado = "Cliente"

        try:
            usuario = Usuario.objects.get(email=email, password=password)
            if not usuario.activo:
                return render(request, "publicos/login.html", {"error": "Tu cuenta ha sido suspendida. Contacta al administrador para más información.", "proximo": proximo})
            if usuario.rol != rol_seleccionado:
                return render(request, "publicos/login.html", {"error": "Rol equivocado. Selecciona el rol correcto para tu cuenta.", "proximo": proximo})

            request.session["logueado"] = {
                "id": usuario.id,
                "nombre": usuario.nombre,
                "rol": usuario.rol
            }

            registrar_ingreso(request, usuario)

            # Si hay un "next" (página a la que quería ir), redirigir allá
            if proximo and proximo.startswith("/"):
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
            return render(request, "publicos/login.html", {"error": "Credenciales incorrectas", "proximo": proximo})

    return render(request, "publicos/login.html", {"proximo": request.GET.get("next", "")})

# LOGOUT
def logout(request):
    if request.session.get("logueado"):
        del request.session["logueado"]
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

        if Usuario.objects.filter(email=email).exists():
            return render(request, "publicos/registro.html", {"error": "Ya existe una cuenta con ese correo."})

        usuario = Usuario.objects.create(
            nombre=nombre,
            apellido=apellido,
            email=email,
            telefono=telefono,
            password=password,
            rol="Cliente"
        )
        request.session["logueado"] = {
            "id": usuario.id,
            "nombre": usuario.nombre,
            "rol": usuario.rol
        }
        registrar_ingreso(request, usuario)
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
    if es_ajax:
        return JsonResponse({
            "cantidad": sum(int(c) for c in carrito.values()),
            "producto_id": producto.id,
        })
    return redirect("sena:usuario_tienda")

def actualizar_carrito(request, producto_id):
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
                request.session["mensaje_carrito"] = f"No hay suficiente stock de {producto.nombre}. Disponible: {stock}."
            if cantidad <= 0:
                del carrito[str(producto_id)]
            else:
                carrito[str(producto_id)] = cantidad
        request.session["carrito"] = carrito
    return redirect("sena:carrito")

def eliminar_carrito(request, producto_id):
    carrito = request.session.get("carrito", {})
    carrito.pop(str(producto_id), None)
    request.session["carrito"] = carrito
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

@autorizacion(["Cliente"])
def usuario_dashboard(request):
    contexto = contexto_carrito(request)
    contexto["productos"] = Producto.objects.all()
    return render(request, "usuarios/usuario_tienda.html", contexto)

@autorizacion(["Cliente"])
def usuario_tienda(request):
    contexto = contexto_carrito(request)
    contexto["productos"] = Producto.objects.all()
    return render(request, "usuarios/usuario_tienda.html", contexto)

@autorizacion(["Cliente"])
def usuario_servicios(request):
    contexto = contexto_carrito(request)
    contexto["servicios"] = SERVICIOS
    return render(request, "usuarios/usuario_servicios.html", contexto)

@autorizacion(["Cliente"])
def usuario_peluquerias(request):
    contexto = contexto_carrito(request)
    contexto["peluquerias"] = Peluqueria.objects.all()
    return render(request, "usuarios/usuario_peluquerias.html", contexto)

@autorizacion(["Cliente"])
def usuario_reservar_cita(request):
    contexto = contexto_carrito(request)
    contexto["peluqueros"] = Usuario.objects.filter(rol="Barbero")
    contexto["peluquerias"] = Peluqueria.objects.all()
    contexto["servicios"] = SERVICIOS
    contexto.update(_horarios_para_template())
    contexto.update(_reservas_para_template())
    return render(request, "usuarios/usuario_reservar_cita.html", contexto)

@autorizacion(["Cliente"])
def usuario_pre_confirmar(request):
    if request.method != "POST":
        return redirect("sena:usuario_reservar_cita")
    peluquero_id = _id_entero(request.POST.get("peluquero"))
    peluqueria_id = _id_entero(request.POST.get("peluqueria"))
    peluquero = Usuario.objects.filter(id=peluquero_id, rol="Barbero").first() if peluquero_id else None
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
        contexto.update({"error": mensaje, "peluqueros": Usuario.objects.filter(rol="Barbero"), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS})
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
    peluquero = Usuario.objects.filter(id=peluquero_id, rol="Barbero").first() if peluquero_id else None
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
        contexto.update({"error": mensaje, "peluqueros": Usuario.objects.filter(rol="Barbero"), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS})
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
        mensaje=f"Nueva cita: {reserva.cliente.nombre} reservó {reserva.servicio} para {reserva.fecha} a las {reserva.hora}.",
    )
    Notificacion.objects.create(
        usuario_id=reserva.cliente_id,
        reserva=reserva,
        mensaje=f"Tu cita de {reserva.servicio} para el {reserva.fecha} a las {reserva.hora} fue reservada correctamente.",
    )
    return redirect("sena:inicio")

@autorizacion(["Cliente"])
def usuario_perfil(request):
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    if request.method == "POST":
        usuario.nombre = request.POST.get("nombre", usuario.nombre)
        usuario.apellido = request.POST.get("apellido", usuario.apellido)
        usuario.telefono = request.POST.get("telefono", usuario.telefono)
        usuario.save()
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
        Notificacion.objects.create(usuario=reserva.peluquero, reserva=reserva, mensaje=f"El cliente canceló la cita del {reserva.fecha} a las {reserva.hora}.")
    else:
        Notificacion.objects.create(usuario=reserva.cliente, reserva=reserva, mensaje=f"La cita está muy próxima para cancelarla en línea. Contacta al barbero: {reserva.peluquero.telefono or 'teléfono no registrado'}.")
    return redirect("sena:usuario_perfil")


@autorizacion(["Cliente"])
def usuario_editar_reserva(request, reserva_id):
    reserva = Reserva.objects.filter(id=reserva_id, cliente_id=request.session["logueado"]["id"]).first()
    if reserva is None or reserva.estado in ["Cancelada", "Completada"]:
        return redirect("sena:usuario_perfil")
    if request.method == "POST":
        fecha = request.POST.get("fecha")
        hora = request.POST.get("hora")
        servicio = request.POST.get("servicio")
        barbero = Usuario.objects.filter(id=request.POST.get("peluquero"), rol="Barbero").first()
        peluqueria = Peluqueria.objects.filter(id=request.POST.get("peluqueria")).first()
        disponible, mensaje = cita_disponible(fecha, hora)
        if disponible and barbero:
            disponible, mensaje = barbero_esta_disponible(barbero.id, fecha, hora, servicio, reserva)
        if disponible and peluqueria:
            reserva.fecha, reserva.hora, reserva.servicio = fecha, hora, servicio
            reserva.peluquero, reserva.peluqueria = barbero, peluqueria
            reserva.estado = "Pendiente"
            reserva.save()
            Notificacion.objects.create(usuario=barbero, reserva=reserva, mensaje=f"Una cita fue modificada: {reserva.fecha} a las {reserva.hora}.")
            return redirect("sena:usuario_perfil")
        return render(request, "usuarios/usuario_editar_reserva.html", {"reserva": reserva, "peluqueros": Usuario.objects.filter(rol="Barbero"), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS, "error": mensaje or "Datos inválidos."})
    return render(request, "usuarios/usuario_editar_reserva.html", {"reserva": reserva, "peluqueros": Usuario.objects.filter(rol="Barbero"), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS})

@autorizacion(["Cliente"])
def usuario_notificaciones(request):
    contexto = contexto_carrito(request)
    contexto["notificaciones"] = Notificacion.objects.filter(
        usuario_id=request.session["logueado"]["id"]
    ).order_by("-fecha")
    return render(request, "usuarios/usuario_notificaciones.html", contexto)

@autorizacion(["Cliente"])
def usuario_confirmar_cita_peluquero(request, reserva_id):
    if request.method != "POST":
        return redirect("sena:usuario_notificaciones")
    reserva = Reserva.objects.filter(
        id=reserva_id, cliente_id=request.session["logueado"]["id"]
    ).first()
    if reserva is None:
        return redirect("sena:usuario_notificaciones")
    reserva.estado = "Confirmada"
    reserva.save()
    Notificacion.objects.filter(
        usuario_id=request.session["logueado"]["id"], reserva=reserva
    ).update(leida=True)
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
    return redirect("sena:usuario_perfil")

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
    citas_hoy = citas.filter(fecha=timezone.now().date())
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
        cita.estado = nuevo_estado
        cita.save()
        if nuevo_estado == "Completada":
            Notificacion.objects.create(
                usuario=cita.cliente,
                reserva=cita,
                mensaje=f"Tu cita de {cita.servicio} del {cita.fecha} fue marcada como completada. ¡Califica tu experiencia!",
            )
    return redirect("sena:peluquero_dashboard")

@autorizacion(["Barbero"])
def peluquero_perfil(request):
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    if request.method == "POST":
        usuario.nombre = request.POST.get("nombre", usuario.nombre)
        usuario.apellido = request.POST.get("apellido", usuario.apellido)
        usuario.telefono = request.POST.get("telefono", usuario.telefono)
        usuario.save()
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
        cliente = Usuario.objects.filter(id=request.POST.get("cliente"), rol="Cliente").first()
        peluqueria = Peluqueria.objects.filter(id=request.POST.get("peluqueria")).first()
        if cliente is None or peluqueria is None:
            return redirect("sena:peluquero_crear_cita")
        disponible, mensaje = cita_disponible(request.POST.get("fecha"), request.POST.get("hora"))
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
            mensaje=f"El barbero {request.session['logueado']['nombre']} agendó una cita de {reserva.servicio} para el {reserva.fecha} a las {reserva.hora}. Confírmala desde tu cuenta.",
        )
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
        if Usuario.objects.filter(email=email).exists():
            return render(request, "administrador/admin_formulario_peluquero.html", {"error": "Ya existe un usuario con ese correo."})
        Usuario.objects.create(nombre=nombre, apellido=apellido, email=email, password=password, telefono=request.POST.get("telefono", "").strip(), rol="Barbero")
        return redirect("sena:admin_peluqueros")
    return render(request, "administrador/admin_formulario_peluquero.html")

@autorizacion(["Admin"])
def admin_editar_peluquero(request, id):
    peluquero = Usuario.objects.get(id=id)
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        if Usuario.objects.exclude(id=id).filter(email=email).exists():
            return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero, "error": "Ese correo ya está registrado."})
        peluquero.nombre = request.POST.get("nombre", "").strip()
        peluquero.apellido = request.POST.get("apellido", "").strip()
        peluquero.email = email
        peluquero.telefono = request.POST.get("telefono", "").strip()
        if request.POST.get("password"):
            peluquero.password = request.POST.get("password")
        peluquero.save()
        return redirect("sena:admin_peluqueros")
    return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero})

@autorizacion(["Admin"])
def admin_eliminar_peluquero(request, id):
    if request.method == "POST":
        Usuario.objects.filter(id=id).delete()
    return redirect("sena:admin_peluqueros")

@autorizacion(["Admin"])
def admin_reservas(request):
    reservas = Reserva.objects.select_related("cliente", "peluquero", "peluqueria").order_by("fecha", "hora")
    return render(request, "administrador/admin_listar_reservas.html", {"datos": reservas})

@autorizacion(["Admin"])
def admin_crear_reserva(request):
    if request.method == "POST":
        cliente = Usuario.objects.filter(id=request.POST.get("cliente"), rol="Cliente").first()
        peluquero = Usuario.objects.filter(id=request.POST.get("peluquero"), rol="Barbero").first()
        if cliente is None or peluquero is None:
            return redirect("sena:admin_crear_reserva")
        disponible, mensaje = cita_disponible(request.POST.get("fecha"), request.POST.get("hora"))
        if disponible:
            disponible, mensaje = barbero_esta_disponible(peluquero.id, request.POST.get("fecha"), request.POST.get("hora"), request.POST.get("servicio"))
        if not disponible:
            return render(request, "administrador/admin_formulario_reserva.html", {"error": mensaje, "clientes": Usuario.objects.filter(rol="Cliente"), "peluqueros": Usuario.objects.filter(rol="Barbero"), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS, "reserva_estados": Reserva.ESTADOS})
        Reserva.objects.create(
            cliente=cliente,
            peluquero=peluquero,
            peluqueria_id=request.POST.get("peluqueria"),
            fecha=request.POST.get("fecha"),
            hora=request.POST.get("hora"),
            servicio=request.POST.get("servicio", "Corte de Cabello"),
            estado=request.POST.get("estado", "Pendiente")
        )
        return redirect("sena:admin_reservas")
    clientes = Usuario.objects.filter(rol="Cliente")
    peluqueros = Usuario.objects.filter(rol="Barbero")
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
    reserva = Reserva.objects.get(id=id)
    if request.method == "POST":
        cliente = Usuario.objects.filter(id=request.POST.get("cliente"), rol="Cliente").first()
        peluquero = Usuario.objects.filter(id=request.POST.get("peluquero"), rol="Barbero").first()
        if cliente is None or peluquero is None:
            return redirect("sena:admin_editar_reserva", id=id)
        reserva.cliente = cliente
        reserva.peluquero = peluquero
        reserva.peluqueria_id = request.POST.get("peluqueria")
        reserva.fecha = request.POST.get("fecha")
        reserva.hora = request.POST.get("hora")
        reserva.servicio = request.POST.get("servicio", reserva.servicio)
        reserva.estado = request.POST.get("estado")
        disponible, mensaje = cita_disponible(request.POST.get("fecha"), request.POST.get("hora"))
        if disponible:
            disponible, mensaje = barbero_esta_disponible(peluquero.id, request.POST.get("fecha"), request.POST.get("hora"), request.POST.get("servicio"), reserva)
        if not disponible:
            return render(request, "administrador/admin_formulario_reserva.html", {"datos": reserva, "error": mensaje, "clientes": Usuario.objects.filter(rol="Cliente"), "peluqueros": Usuario.objects.filter(rol="Barbero"), "peluquerias": Peluqueria.objects.all(), "servicios": SERVICIOS, "reserva_estados": Reserva.ESTADOS})
        reserva.save()
        return redirect("sena:admin_reservas")
    clientes = Usuario.objects.filter(rol="Cliente")
    peluqueros = Usuario.objects.filter(rol="Barbero")
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
        Reserva.objects.filter(id=id).delete()
    return redirect("sena:admin_reservas")

@autorizacion(["Admin"])
def admin_cancelar_reserva(request, id):
    if request.method == "POST":
        Reserva.objects.filter(id=id).update(estado="Cancelada")
    return redirect("sena:admin_reservas")

@autorizacion(["Admin"])
def admin_horarios(request):
    peluquerias = Peluqueria.objects.all()
    peluqueria_id = request.GET.get("peluqueria") or request.POST.get("peluqueria_seleccionada") or (str(peluquerias.first().id) if peluquerias.exists() else None)
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
        elif accion == "crear_bloqueo":
            fecha = request.POST.get("fecha")
            hora = request.POST.get("hora") or None
            if fecha and peluqueria_actual:
                BloqueoHorario.objects.create(fecha=fecha, hora=hora, motivo=request.POST.get("motivo", ""), peluqueria=peluqueria_actual)
        return redirect(f"{reverse('sena:admin_horarios')}?peluqueria={peluqueria_id}")
    horarios = HorarioTrabajo.objects.filter(peluqueria=peluqueria_actual).order_by("dia_semana") if peluqueria_actual else []
    bloqueos = BloqueoHorario.objects.filter(peluqueria=peluqueria_actual) if peluqueria_actual else BloqueoHorario.objects.none()
    return render(request, "administrador/admin_horarios.html", {"horarios": horarios, "bloqueos": bloqueos, "hoy": datetime.today().date(), "peluquerias": peluquerias, "peluqueria_actual": peluqueria_actual})

@autorizacion(["Admin"])
def admin_eliminar_bloqueo(request, id):
    if request.method == "POST":
        BloqueoHorario.objects.filter(id=id).delete()
    return redirect("sena:admin_horarios")


@autorizacion(["Admin"])
def admin_peluquerias(request):
    return render(request, "administrador/admin_peluquerias.html", {"peluquerias": Peluqueria.objects.all()})


@autorizacion(["Admin"])
def admin_crear_peluqueria(request):
    if request.method == "POST":
        Peluqueria.objects.create(nombre=request.POST.get("nombre"), ubicacion=request.POST.get("ubicacion"), telefono=request.POST.get("telefono"))
        return redirect("sena:admin_peluquerias")
    return render(request, "administrador/admin_formulario_peluqueria.html")


@autorizacion(["Admin"])
def admin_editar_peluqueria(request, id):
    peluqueria = Peluqueria.objects.get(id=id)
    if request.method == "POST":
        peluqueria.nombre = request.POST.get("nombre")
        peluqueria.ubicacion = request.POST.get("ubicacion")
        peluqueria.telefono = request.POST.get("telefono")
        peluqueria.save()
        return redirect("sena:admin_peluquerias")
    return render(request, "administrador/admin_formulario_peluqueria.html", {"peluqueria": peluqueria})


@autorizacion(["Admin"])
def admin_eliminar_peluqueria(request, id):
    if request.method == "POST":
        Peluqueria.objects.filter(id=id).delete()
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
    producto.precio = request.POST.get("precio", 0)
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
        return redirect("sena:admin_productos")
    return render(request, "administrador/admin_formulario_producto.html", {"categorias": Producto.CATEGORIAS})


@autorizacion(["Admin"])
def admin_editar_producto(request, id):
    producto = Producto.objects.get(id=id)
    if request.method == "POST":
        datos_producto(request, producto)
        return redirect("sena:admin_productos")
    return render(request, "administrador/admin_formulario_producto.html", {"producto": producto, "categorias": Producto.CATEGORIAS})


@autorizacion(["Admin"])
def admin_eliminar_producto(request, id):
    if request.method == "POST":
        Producto.objects.filter(id=id).delete()
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
        if not all([nombre, apellido, email, password, rol]):
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": "Todos los campos son obligatorios"
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
            password=password,
            telefono=telefono,
            rol=rol
        )
        return redirect("sena:admin_usuarios")

    return render(request, "administrador/admin_formulario_usuario.html", {
        "roles": Usuario.ROLES
    })

@autorizacion(["Admin"])
def admin_editar_usuario(request, id):
    """Editar usuario existente"""
    usuario = Usuario.objects.get(id=id)
    
    if request.method == "POST":
        usuario.nombre = request.POST.get("nombre", usuario.nombre).strip()
        usuario.apellido = request.POST.get("apellido", usuario.apellido).strip()
        usuario.email = request.POST.get("email", usuario.email).strip()
        usuario.telefono = request.POST.get("telefono", usuario.telefono).strip()
        usuario.rol = request.POST.get("rol", usuario.rol)
        
        # Actualizar contraseña si se proporciona
        password = request.POST.get("password", "").strip()
        if password:
            usuario.password = password
        
        usuario.save()
        return redirect("sena:admin_usuarios")
    
    return render(request, "administrador/admin_formulario_usuario.html", {
        "usuario": usuario,
        "roles": Usuario.ROLES,
        "editar": True
    })

@autorizacion(["Admin"])
def admin_eliminar_usuario(request, id):
    if request.method == "POST":
        Usuario.objects.filter(id=id).delete()
    return redirect("sena:admin_usuarios")

@autorizacion(["Admin"])
def admin_suspender_usuario(request, id):
    """Suspender o activar un usuario"""
    if request.method == "POST":
        usuario = Usuario.objects.filter(id=id).first()
        if usuario and usuario.rol != "Admin":
            usuario.activo = not usuario.activo
            usuario.save()
    return redirect("sena:admin_usuarios")
