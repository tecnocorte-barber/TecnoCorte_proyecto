"""Implementaci?n agrupada del dominio."""
from .core import *
from .core import _id_entero, _peluqueria_del_barbero, _motivo_eliminacion, _respuesta_reporte_excel, _datos_notificacion, _datos_descargables, _pestanas_config

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
        registrar_accion(request, "actualizar_cita", "Reserva", cita.id, f"Estado: {estado_anterior} â†’ {nuevo_estado}")
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

