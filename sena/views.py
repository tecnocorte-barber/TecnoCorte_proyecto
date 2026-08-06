from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import Usuario, Peluqueria, Producto, Reserva, Pedido, PedidoProducto
from .utilidades import autorizacion

SERVICIOS = [
    {"nombre": "Corte de Cabello", "descripcion": "Lavado, corte preciso con tijera y máquina, peinado con productos premium.", "duracion": "45 Minutos", "precio": 45000},
    {"nombre": "Arreglo de Barba", "descripcion": "Toalla caliente, perfilado exacto, hidratación con aceites esenciales.", "duracion": "30 Minutos", "precio": 35000},
    {"nombre": "Combo Completo", "descripcion": "Corte de cabello + arreglo de barba + limpieza facial.", "duracion": "1 Hora 15 Min", "precio": 75000},
]

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
    return {"items": items, "total": total, "cantidad": cantidad, "carrito": carrito}

# INICIO - Sin login
def inicio(request):
    if request.session.get("logueado"):
        rol = request.session["logueado"]["rol"]
        if rol == "Admin":
            return redirect("sena:admin_reservas")
        elif rol == "Peluquero":
            return redirect("sena:peluquero_dashboard")
        else:
            return redirect("sena:usuario_dashboard")
    contexto = contexto_carrito(request)
    return render(request, "index.html", contexto)

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
            if usuario.rol != rol_seleccionado:
                return render(request, "login.html", {"error": "Rol equivocado. Selecciona el rol correcto para tu cuenta.", "proximo": proximo})

            request.session["logueado"] = {
                "id": usuario.id,
                "nombre": usuario.nombre,
                "rol": usuario.rol
            }

            if proximo == "carrito":
                return redirect("sena:carrito")

            if usuario.rol == "Admin":
                return redirect("sena:admin_reservas")
            elif usuario.rol == "Peluquero":
                return redirect("sena:peluquero_dashboard")
            else:
                return redirect("sena:usuario_dashboard")
        except Exception:
            return render(request, "login.html", {"error": "Credenciales incorrectas", "proximo": proximo})

    return render(request, "login.html", {"proximo": request.GET.get("next", "")})

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
            return render(request, "registro.html", {"error": "Completa todos los campos obligatorios."})

        if Usuario.objects.filter(email=email).exists():
            return render(request, "registro.html", {"error": "Ya existe una cuenta con ese correo."})

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
        if proximo == "carrito":
            return redirect("sena:carrito")
        return redirect("sena:usuario_dashboard")

    return render(request, "registro.html", {"proximo": request.GET.get("next", "")})

# PÁGINAS PÚBLICAS
def como_funciona(request):
    return render(request, "como_funciona.html")

def sobre_nosotros(request):
    return render(request, "sobre_nosotros.html")

def ayuda(request):
    contexto = contexto_carrito(request)
    return render(request, "ayuda.html", contexto)

# ═══════════════════════════════════════════════════════════════════════════
# CARRITO DE COMPRAS (funciona sin estar registrado)
# ═══════════════════════════════════════════════════════════════════════════

def carrito(request):
    contexto = contexto_carrito(request)
    return render(request, "carrito.html", contexto)

def agregar_carrito(request, producto_id):
    es_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    try:
        producto = Producto.objects.get(id=producto_id, disponible=True)
    except Producto.DoesNotExist:
        if es_ajax:
            return JsonResponse({"error": "Producto no disponible"}, status=404)
        return redirect("sena:usuario_tienda")
    carrito = request.session.get("carrito", {})
    carrito[str(producto.id)] = int(carrito.get(str(producto.id), 0)) + 1
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
        pedido = Pedido.objects.create(
            cliente_id=cliente_id,
            total=contexto["total"],
            estado="Pendiente"
        )
        for item in contexto["items"]:
            PedidoProducto.objects.create(
                pedido=pedido,
                producto=item["producto"],
                cantidad=item["cantidad"],
                precio=item["producto"].precio
            )
            producto = item["producto"]
            if producto.stock is not None:
                producto.stock = max(0, producto.stock - item["cantidad"])
                if producto.stock == 0:
                    producto.disponible = False
                producto.save()
        request.session["carrito"] = {}
        return redirect("sena:pedido_exitoso", pedido_id=pedido.id)

    return render(request, "finalizar_pedido.html", contexto)

@autorizacion(["Cliente"])
def pedido_exitoso(request, pedido_id):
    pedido = Pedido.objects.filter(id=pedido_id, cliente_id=request.session["logueado"]["id"]).first()
    if pedido is None:
        return redirect("sena:usuario_perfil")
    return render(request, "pedido_exitoso.html", {"pedido": pedido})

# ═══════════════════════════════════════════════════════════════════════════
# USUARIO/CLIENTE
# ═══════════════════════════════════════════════════════════════════════════

@autorizacion(["Cliente"])
def usuario_dashboard(request):
    contexto = contexto_carrito(request)
    contexto["productos"] = Producto.objects.all()
    return render(request, "usuario_tienda.html", contexto)

def usuario_tienda(request):
    contexto = contexto_carrito(request)
    contexto["productos"] = Producto.objects.all()
    return render(request, "usuario_tienda.html", contexto)

def usuario_servicios(request):
    contexto = contexto_carrito(request)
    contexto["servicios"] = SERVICIOS
    return render(request, "usuario_servicios.html", contexto)

def usuario_peluquerias(request):
    contexto = contexto_carrito(request)
    contexto["peluquerias"] = Peluqueria.objects.all()
    return render(request, "usuario_peluquerias.html", contexto)

@autorizacion(["Cliente"])
def usuario_reservar_cita(request):
    contexto = contexto_carrito(request)
    contexto["peluqueros"] = Usuario.objects.filter(rol="Peluquero")
    contexto["peluquerias"] = Peluqueria.objects.all()
    contexto["servicios"] = SERVICIOS
    return render(request, "usuario_reservar_cita.html", contexto)

@autorizacion(["Cliente"])
def usuario_pre_confirmar(request):
    if request.method != "POST":
        return redirect("sena:usuario_reservar_cita")
    peluquero = Usuario.objects.filter(id=request.POST.get("peluquero"), rol="Peluquero").first()
    peluqueria = Peluqueria.objects.filter(id=request.POST.get("peluqueria")).first()
    if peluquero is None or peluqueria is None:
        return redirect("sena:usuario_reservar_cita")
    datos = {
        "servicio": request.POST.get("servicio", "Corte de Cabello"),
        "peluquero": peluquero,
        "peluqueria": peluqueria,
        "fecha": request.POST.get("fecha", ""),
        "hora": request.POST.get("hora", ""),
    }
    contexto = contexto_carrito(request)
    contexto["datos"] = datos
    return render(request, "usuario_confirmar_reserva.html", contexto)

@autorizacion(["Cliente"])
def usuario_confirmar_reserva(request):
    if request.method != "POST":
        return redirect("sena:usuario_reservar_cita")
    Reserva.objects.create(
        cliente_id=request.session["logueado"]["id"],
        peluquero_id=request.POST.get("peluquero"),
        peluqueria_id=request.POST.get("peluqueria"),
        fecha=request.POST.get("fecha"),
        hora=request.POST.get("hora"),
        servicio=request.POST.get("servicio", "Corte de Cabello")
    )
    return redirect("sena:usuario_dashboard")

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
    contexto = contexto_carrito(request)
    contexto["usuario"] = usuario
    contexto["citas"] = citas
    contexto["pedidos"] = pedidos
    return render(request, "usuario_perfil.html", contexto)

# ═══════════════════════════════════════════════════════════════════════════
# PELUQUERO
# ═══════════════════════════════════════════════════════════════════════════

@autorizacion(["Peluquero"])
def peluquero_dashboard(request):
    citas = Reserva.objects.filter(peluquero_id=request.session["logueado"]["id"]).order_by("fecha", "hora")
    return render(request, "peluquero_dashboard.html", {"citas": citas})

@autorizacion(["Peluquero"])
def peluquero_perfil(request):
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    if request.method == "POST":
        usuario.nombre = request.POST.get("nombre", usuario.nombre)
        usuario.apellido = request.POST.get("apellido", usuario.apellido)
        usuario.save()
        return redirect("sena:peluquero_dashboard")
    return render(request, "usuario_perfil.html", {"usuario": usuario})

@autorizacion(["Peluquero"])
def peluquero_crear_cita(request):
    if request.method == "POST":
        cliente = Usuario.objects.filter(id=request.POST.get("cliente"), rol="Cliente").first()
        peluqueria = Peluqueria.objects.filter(id=request.POST.get("peluqueria")).first()
        if cliente is None or peluqueria is None:
            return redirect("sena:peluquero_crear_cita")
        Reserva.objects.create(
            cliente=cliente,
            peluquero_id=request.session["logueado"]["id"],
            peluqueria=peluqueria,
            fecha=request.POST.get("fecha"),
            hora=request.POST.get("hora"),
            servicio=request.POST.get("servicio", "Corte de Cabello"),
            estado=request.POST.get("estado", "Pendiente"),
        )
        return redirect("sena:peluquero_dashboard")
    contexto = {
        "clientes": Usuario.objects.filter(rol="Cliente"),
        "peluquerias": Peluqueria.objects.all(),
        "servicios": SERVICIOS,
        "reserva_estados": Reserva.ESTADOS,
    }
    return render(request, "peluquero_crear_cita.html", contexto)

# ═══════════════════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════════════════

@autorizacion(["Admin"])
def admin_dashboard(request):
    return redirect("sena:admin_reservas")

@autorizacion(["Admin"])
def admin_peluqueros(request):
    peluqueros = Usuario.objects.filter(rol="Peluquero")
    return render(request, "admin_listar_peluqueros.html", {"datos": peluqueros})

@autorizacion(["Admin"])
def admin_crear_peluquero(request):
    if request.method == "POST":
        Usuario.objects.create(
            nombre=request.POST.get("nombre"),
            apellido=request.POST.get("apellido"),
            email=request.POST.get("email"),
            password=request.POST.get("password"),
            telefono=request.POST.get("telefono", ""),
            rol="Peluquero"
        )
        return redirect("sena:admin_peluqueros")
    return render(request, "admin_formulario_peluquero.html")

@autorizacion(["Admin"])
def admin_editar_peluquero(request, id):
    peluquero = Usuario.objects.get(id=id)
    if request.method == "POST":
        peluquero.nombre = request.POST.get("nombre")
        peluquero.apellido = request.POST.get("apellido")
        peluquero.email = request.POST.get("email")
        peluquero.telefono = request.POST.get("telefono")
        peluquero.save()
        return redirect("sena:admin_peluqueros")
    return render(request, "admin_formulario_peluquero.html", {"datos": peluquero})

@autorizacion(["Admin"])
def admin_eliminar_peluquero(request, id):
    Usuario.objects.get(id=id).delete()
    return redirect("sena:admin_peluqueros")

@autorizacion(["Admin"])
def admin_reservas(request):
    reservas = Reserva.objects.all()
    return render(request, "admin_listar_reservas.html", {"data": reservas})

@autorizacion(["Admin"])
def admin_crear_reserva(request):
    if request.method == "POST":
        cliente = Usuario.objects.filter(id=request.POST.get("cliente"), rol="Cliente").first()
        peluquero = Usuario.objects.filter(id=request.POST.get("peluquero"), rol="Peluquero").first()
        if cliente is None or peluquero is None:
            return redirect("sena:admin_crear_reserva")
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
    peluqueros = Usuario.objects.filter(rol="Peluquero")
    peluquerias = Peluqueria.objects.all()
    return render(request, "admin_formulario_reserva.html", {
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
        peluquero = Usuario.objects.filter(id=request.POST.get("peluquero"), rol="Peluquero").first()
        if cliente is None or peluquero is None:
            return redirect("sena:admin_editar_reserva", id=id)
        reserva.cliente = cliente
        reserva.peluquero = peluquero
        reserva.peluqueria_id = request.POST.get("peluqueria")
        reserva.fecha = request.POST.get("fecha")
        reserva.hora = request.POST.get("hora")
        reserva.servicio = request.POST.get("servicio", reserva.servicio)
        reserva.estado = request.POST.get("estado")
        reserva.save()
        return redirect("sena:admin_reservas")
    clientes = Usuario.objects.filter(rol="Cliente")
    peluqueros = Usuario.objects.filter(rol="Peluquero")
    peluquerias = Peluqueria.objects.all()
    return render(request, "admin_formulario_reserva.html", {
        "datos": reserva,
        "clientes": clientes,
        "peluqueros": peluqueros,
        "peluquerias": peluquerias,
        "servicios": SERVICIOS,
        "reserva_estados": Reserva.ESTADOS
    })

@autorizacion(["Admin"])
def admin_eliminar_reserva(request, id):
    Reserva.objects.get(id=id).delete()
    return redirect("sena:admin_reservas")

@autorizacion(["Admin"])
def admin_perfil(request):
    usuario = Usuario.objects.get(id=request.session["logueado"]["id"])
    if request.method == "POST":
        usuario.nombre = request.POST.get("nombre", usuario.nombre)
        usuario.apellido = request.POST.get("apellido", usuario.apellido)
        usuario.save()
        return redirect("sena:admin_dashboard")
    return render(request, "usuario_perfil.html", {"usuario": usuario})
