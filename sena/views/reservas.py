"""Implementaci?n agrupada del dominio."""
from .core import *
from .core import _id_entero, _horarios_para_template, _reservas_para_template, _invalidar_cache_disponibilidad, _peluqueria_del_barbero, _datos_notificacion, _datos_descargables, _pestanas_config

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

