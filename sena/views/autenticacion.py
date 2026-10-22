"""Autenticación web y verificación de registros por correo."""
import hashlib
import hmac
import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

from .core import *  # Reutiliza configuraci?n, modelos y helpers compartidos.
from ..models import RegistroPendiente
from ..services.autenticacion import (
    crear_codigo_verificacion,
    enviar_codigo_verificacion,
    url_publica,
)
from ..services.correos import enviar_correo_destino

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
            if settings.REQUIRE_EMAIL_VERIFICATION and not usuario.email_verificado:
                return render(request, "publicos/login.html", {
                    "error": "Verifica tu correo antes de iniciar sesión.",
                    "usuario_id_verificacion": usuario.id,
                    "proximo": proximo,
                })
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
        clave_recuperacion = f"recuperacion_{email}_{request.META.get('REMOTE_ADDR', '')}"
        if cache.get(clave_recuperacion):
            # Respuesta idéntica a la válida: no revela si un correo existe.
            return render(request, "publicos/recuperar_password.html", {"enviado": True})
        cache.set(clave_recuperacion, True, settings.EMAIL_VERIFICATION_RESEND_SECONDS)
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
        usuario.sesion_version += 1
        usuario.save(update_fields=["password", "sesion_version"])
        messages.success(request, "Contraseña actualizada. Ya puedes iniciar sesión.")
        return redirect("sena:login")
    return render(request, "publicos/restablecer_password.html", {"valido": True})


def logout(request):
    guardar_carrito_activo(request)
    sesion = request.session.get("logueado")
    if sesion:
        Usuario.objects.filter(id=sesion.get("id"), activo=True).update(sesion_version=models.F("sesion_version") + 1)
        del request.session["logueado"]
    request.session.pop("carrito_usuario_id", None)
    request.session["carrito"] = request.session.get("carritos_usuario", {}).get("anonimo", {})
    return redirect("sena:inicio")


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
            "pendiente": pendiente,
            "token": token,
            "proximo": proximo,
            "enviado": enviado,
        })

    return render(request, "publicos/registro.html", {"proximo": request.GET.get("next", "")})


def _pendiente_por_token(token):
    if not token:
        return None
    hash_token = hashlib.sha256(token.encode()).hexdigest()
    candidatos = RegistroPendiente.objects.all()
    return next((item for item in candidatos if hmac.compare_digest(item.token_hash, hash_token)), None)


def _iniciar_usuario_verificado(request, pendiente, proximo=""):
    with transaction.atomic():
        pendiente = RegistroPendiente.objects.select_for_update().get(pk=pendiente.pk)
        if Usuario.objects.filter(email__iexact=pendiente.email).exists():
            pendiente.delete()
            return redirect("sena:login")
        usuario = Usuario.objects.create(
            nombre=pendiente.nombre, apellido=pendiente.apellido,
            email=pendiente.email, telefono=pendiente.telefono,
            password=pendiente.password, rol="Cliente", email_verificado=True,
        )
        pendiente.delete()
    admins = list(Usuario.objects.filter(rol="Admin", activo=True).only("id"))
    if admins:
        Notificacion.objects.bulk_create([
            Notificacion(usuario=admin, mensaje=f"Nuevo cliente registrado: {usuario.nombre} {usuario.apellido}.")
            for admin in admins
        ])
    guardar_carrito_activo(request)
    request.session["logueado"] = {"id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol, "sesion_version": usuario.sesion_version}
    cargar_carrito_usuario(request, usuario.id)
    registrar_ingreso(request, usuario)
    messages.success(request, f"Correo verificado. Bienvenido a TecnoCorte, {usuario.nombre}.")
    if proximo and url_has_allowed_host_and_scheme(proximo, {request.get_host()}, require_https=request.is_secure()):
        return redirect(proximo)
    return redirect("sena:inicio")


def verificar_correo(request):
    token = request.POST.get("token") or request.GET.get("token") or request.session.get("registro_pendiente_token", "")
    pendiente = _pendiente_por_token(token)
    proximo = request.POST.get("next") or request.GET.get("next") or request.session.get("registro_pendiente_next", "")
    if pendiente is None:
        return render(request, "publicos/verificar_correo.html", {"error": "El enlace de verificación no es válido o ya expiró."})
    if pendiente.token_expira <= timezone.now():
        return render(request, "publicos/verificar_correo.html", {"pendiente": pendiente, "token": token, "proximo": proximo, "error": "El enlace expiró. Puedes solicitar un nuevo código."})
    if request.method == "GET" and request.GET.get("token"):
        return render(request, "publicos/verificar_correo.html", {"pendiente": pendiente, "token": token, "proximo": proximo, "enlace_directo": True})
    if request.method == "POST":
        if request.POST.get("confirmar_enlace") == "1":
            return _iniciar_usuario_verificado(request, pendiente, proximo)
        codigo = request.POST.get("codigo", "").strip()
        hash_codigo = hashlib.sha256(codigo.encode()).hexdigest()
        if (not pendiente.codigo_expira or pendiente.codigo_expira <= timezone.now() or
                not hmac.compare_digest(hash_codigo, pendiente.codigo_hash)):
            return render(request, "publicos/verificar_correo.html", {"pendiente": pendiente, "token": token, "proximo": proximo, "error": "El código no es válido o ya expiró."})
        return _iniciar_usuario_verificado(request, pendiente, proximo)
    return render(request, "publicos/verificar_correo.html", {"pendiente": pendiente, "token": token, "proximo": proximo})


def reenviar_verificacion(request):
    token = request.POST.get("token") or request.GET.get("token") or request.session.get("registro_pendiente_token", "")
    pendiente = _pendiente_por_token(token)
    if pendiente is None:
        return render(request, "publicos/verificar_correo.html", {"error": "El registro pendiente ya no es válido. Vuelve a registrarte."})
    clave = f"verificacion_reenvio_{pendiente.email}_{request.META.get('REMOTE_ADDR', '')}"
    if cache.get(clave):
        return render(request, "publicos/verificar_correo.html", {"pendiente": pendiente, "token": token, "error": "Espera un minuto antes de solicitar otro código."})
    ruta = reverse("sena:verificar_correo")
    enviado, nuevo_token = enviar_codigo_verificacion(request, pendiente, lambda value: url_publica(request, f"{ruta}?token={value}"))
    cache.set(clave, True, settings.EMAIL_VERIFICATION_RESEND_SECONDS)
    request.session["registro_pendiente_token"] = nuevo_token
    return render(request, "publicos/verificar_correo.html", {"pendiente": pendiente, "token": nuevo_token, "enviado": enviado})


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
