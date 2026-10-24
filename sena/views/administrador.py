"""Implementaci?n agrupada del dominio."""
from .core import *
from .core import _id_entero, _peluqueria_del_barbero, _motivo_eliminacion, _respuesta_reporte_excel, _datos_notificacion, _datos_descargables, _pestanas_config, _borrar_archivo
from ..services.pedidos import actualizar_pedido

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
        config.save()
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
    respuesta = _respuesta_reporte_excel("Reporte de reservas Â· TecnoCorte", "Reservas registradas", ["ID", "Fecha", "Hora", "Cliente", "Barbero", "Barbería", "Servicio", "Estado"], filas, "reservas_tecnocorte.xls")
    return respuesta


@autorizacion(["Admin"])
def admin_exportar_pedidos(request):
    """Descarga un reporte compatible con Excel de los pedidos."""
    pedidos = Pedido.objects.select_related("cliente").order_by("-fecha")
    filas = [(p.id, f"{p.fecha:%d/%m/%Y %H:%M}", f"{p.cliente.nombre} {p.cliente.apellido}", p.cliente.email, p.total, p.estado, "Sí" if p.pago_confirmado else "No") for p in pedidos]
    return _respuesta_reporte_excel("Reporte de pedidos Â· TecnoCorte", "Pedidos registrados", ["ID", "Fecha", "Cliente", "Correo", "Total COP", "Estado", "Pago confirmado"], filas, "pedidos_tecnocorte.xls")


@autorizacion(["Admin"])
def admin_peluqueros(request):
    peluqueros = Usuario.objects.filter(rol="Barbero")
    return render(request, "administrador/admin_listar_peluqueros.html", {"datos": peluqueros})


@autorizacion(["Admin"])
def admin_crear_peluquero(request):
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
        if request.POST.get("password"):
            # Solo se actualiza si la nueva contraseña cumple las reglas
            error_password = validar_password(request.POST.get("password"))
            if error_password:
                return render(request, "administrador/admin_formulario_peluquero.html", {"datos": peluquero, "error": error_password, "peluquerias": Peluqueria.objects.all()})
            peluquero.password = make_password(request.POST.get("password"))
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
        registrar_accion(request, "actualizar_cita", "Reserva", reserva.id, f"Estado: {estado_anterior} â†’ {estado_nuevo}")
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
        if reserva:
            Notificacion.objects.create(usuario=reserva.cliente, mensaje=f"La reserva #{reserva.id} fue eliminada por el administrador.")
            Notificacion.objects.create(usuario=reserva.peluquero, mensaje=f"La reserva #{reserva.id} fue eliminada por el administrador.")
            enviar_correo_cita(request, reserva.cliente, "Reserva eliminada en TecnoCorte", f"Tu reserva #{reserva.id} del {formato_cita(reserva)} fue eliminada por el administrador.")
            enviar_correo_cita(request, reserva.peluquero, "Reserva eliminada en TecnoCorte", f"La reserva #{reserva.id} del {formato_cita(reserva)} fue eliminada por el administrador.")
            reserva.delete()
            messages.info(request, "La reserva fue eliminada y se notificó a sus participantes.")
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
            avisar_foto_eliminada(peluqueria.dueno, f"la foto principal de Â«{peluqueria.nombre}Â»", motivo, request)
            messages.success(request, f"Foto principal de Â«{peluqueria.nombre}Â» eliminada.")
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
        avisar_foto_eliminada(dueno, f"una foto de la galería de Â«{nombre}Â»", motivo, request)
        messages.success(request, f"Foto eliminada de la galería de Â«{nombre}Â».")
    return redirect("sena:admin_galeria")


@autorizacion(["Admin"])
def admin_productos(request):
    return render(request, "administrador/admin_productos.html", {"productos": Producto.objects.all().order_by("nombre")})


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
            messages.success(request, f"Foto de Â«{producto.nombre}Â» eliminada.")
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
                messages.error(request, f"Â«{solicitud.nombre}Â» ya existe para {solicitud.barbero.nombre}.")
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
                    mensaje=f"El administrador creó tu servicio Â«{solicitud.nombre}Â» por ${solicitud.precio} COP.",
                )
                messages.success(request, f"Servicio Â«{solicitud.nombre}Â» creado para {solicitud.barbero.nombre}.")

        elif request.POST.get("accion") == "rechazar":
            solicitud.estado = "rechazada"
            solicitud.resuelta = timezone.now()
            solicitud.nota_admin = nota
            solicitud.save()
            mensaje = f"El administrador rechazó tu solicitud del servicio Â«{solicitud.nombre}Â»."
            if nota:
                mensaje += f" Motivo: {nota}"
            Notificacion.objects.create(usuario=solicitud.barbero, mensaje=mensaje)
            messages.info(request, f"Solicitud de Â«{solicitud.nombre}Â» rechazada.")

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
        foto = request.FILES.get("foto")
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
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        rol = request.POST.get("rol", "Cliente")

        # Validaciones
        if not all([nombre, apellido, email, password, rol]) or rol not in dict(Usuario.ROLES):
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": "Todos los campos son obligatorios",
                "roles": Usuario.ROLES,
                "peluquerias": Peluqueria.objects.all(),
            })
        error_telefono = validar_telefono(telefono)
        if error_telefono:
            return render(request, "administrador/admin_formulario_usuario.html", {"error": error_telefono, "roles": Usuario.ROLES, "peluquerias": Peluqueria.objects.all()})

        try:
            validate_email(email)
        except ValidationError:
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": "Ese correo no tiene un formato válido",
                "roles": Usuario.ROLES,
                "peluquerias": Peluqueria.objects.all(),
            })

        error_password = validar_password(password)
        if error_password:
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": error_password,
                "roles": Usuario.ROLES,
                "peluquerias": Peluqueria.objects.all(),
            })

        if Usuario.objects.filter(email__iexact=email).exists():
            return render(request, "administrador/admin_formulario_usuario.html", {
                "error": f"Ya existe un usuario con el email {email}",
                "roles": Usuario.ROLES,
                "peluquerias": Peluqueria.objects.all(),
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
            return render(request, "administrador/admin_formulario_usuario.html", {"error": error_imagen, "roles": Usuario.ROLES, "peluquerias": Peluqueria.objects.all()})
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
    })


@autorizacion(["Admin"])
def admin_editar_usuario(request, id):
    """Editar usuario existente"""
    usuario = get_object_or_404(Usuario, id=id)
    
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
        nuevo_rol = request.POST.get("rol", usuario.rol)
        # El rol de un administrador no se puede modificar
        if usuario.rol == "Admin":
            nuevo_rol = "Admin"
        if nuevo_rol not in dict(Usuario.ROLES):
            return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": "El rol seleccionado no es válido.", "peluquerias": Peluqueria.objects.all()})
        usuario.rol = nuevo_rol
        peluqueria_id = _id_entero(request.POST.get("peluqueria"))
        if nuevo_rol == "Barbero":
            if not peluqueria_id or not Peluqueria.objects.filter(id=peluqueria_id).exists():
                return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": "Para un barbero debes seleccionar la barbería a la que pertenece.", "peluquerias": Peluqueria.objects.all()})
            usuario.peluqueria_id = peluqueria_id
        else:
            usuario.peluqueria = None
        foto = request.FILES.get("foto")
        error_imagen = validar_imagen(foto)
        if error_imagen:
            return render(request, "administrador/admin_formulario_usuario.html", {"usuario": usuario, "roles": Usuario.ROLES, "editar": True, "error": error_imagen, "peluquerias": Peluqueria.objects.all()})
        if foto:
            usuario.foto = foto
        elif request.POST.get("quitar_foto") and usuario.foto:
            # El Admin puede quitar la foto actual desde el formulario.
            _borrar_archivo(usuario.foto)
            usuario.foto = None

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
        "editar": True,
        "peluquerias": Peluqueria.objects.all(),
    })


@autorizacion(["Admin"])
def admin_eliminar_usuario(request, id):
    if request.method == "POST":
        usuario = Usuario.objects.filter(id=id).exclude(id=request.session["logueado"]["id"]).first()
        if usuario:
            nombre = f"{usuario.nombre} {usuario.apellido}"
            try:
                foto_archivo = usuario.foto
                usuario.delete()
                if foto_archivo:
                    _borrar_archivo(foto_archivo)
                registrar_accion(request, "eliminar_usuario", "Usuario", id, f"Usuario eliminado: {nombre}")
                messages.success(request, f"El usuario {nombre} fue eliminado correctamente.")
            except ProtectedError:
                messages.error(request, "No se puede eliminar este usuario porque tiene citas o pedidos asociados. Puedes suspenderlo para conservar el historial.")
        else:
            messages.error(request, "No puedes eliminar tu propia cuenta o el usuario no existe.")
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
