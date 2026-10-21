"""Implementaci?n agrupada del dominio."""
from .core import *
from .core import _id_entero, _horarios_para_template, _reservas_para_template, _invalidar_cache_disponibilidad, _peluqueria_del_barbero, _datos_notificacion, _datos_descargables, _pestanas_config

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
    return render(request, "usuarios/usuario_perfil.html", contexto)


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


@autorizacion(["Cliente"])
def usuario_notificaciones(request):
    contexto = contexto_carrito(request)
    contexto["notificaciones"] = Notificacion.objects.filter(
        usuario_id=request.session["logueado"]["id"]
    ).order_by("-fecha")
    contexto["calificaciones_reservas"] = set(
        Calificacion.objects.filter(cliente_id=request.session["logueado"]["id"]).values_list("reserva_id", flat=True)
    )
    return render(request, "usuarios/usuario_notificaciones.html", contexto)


@autorizacion(["Cliente"])
def usuario_marcar_notificaciones_leidas(request):
    if request.method == "POST":
        Notificacion.objects.filter(usuario_id=request.session["logueado"]["id"], leida=False).update(leida=True)
        messages.success(request, "Todas tus notificaciones están marcadas como leídas.")
    return redirect("sena:usuario_notificaciones")

