"""Implementaci?n de vistas agrupadas."""
from .core import *  # Reutiliza configuraci?n, modelos y helpers compartidos.

def inicio(request):
    # El Admin y el Barbero trabajan en su panel, pero el Admin puede abrir el
    # inicio con ?vista=publica para revisarlo o usar el botón "Editar inicio".
    if request.session.get("logueado") and request.GET.get("vista") != "publica":
        rol = request.session["logueado"]["rol"]
        if rol in ("Admin", "SuperAdmin"):
            return redirect("sena:admin_dashboard")
        elif rol == "Barbero":
            return redirect("sena:peluquero_dashboard")
    contexto = contexto_carrito(request)
    contexto.update(contenido_inicio())
    return render(request, "publicos/index.html", contexto)


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

