# Funciones de ayuda del proyecto: validación de contraseñas y control de acceso por roles
from django.shortcuts import redirect
from django.urls import reverse
from functools import wraps
import re

# Reglas de contraseña: mínimo 8 caracteres, una mayúscula, un número y un símbolo
def validar_password(password):
    """Devuelve un mensaje de error si la contraseña no cumple las reglas, o "" si es válida."""
    if len(password or "") < 8:
        return "La contraseña debe tener mínimo 8 caracteres."
    if not re.search(r"[A-Z]", password):
        return "La contraseña debe tener al menos una letra mayúscula."
    if not re.search(r"[0-9]", password):
        return "La contraseña debe tener al menos un número."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "La contraseña debe tener al menos un símbolo (ej: !@#$%)."
    return ""

# Decorador que protege vistas: exige sesión iniciada y, opcionalmente, un rol permitido
def autorizacion(roles=[]):
    def decorador(vista):
        @wraps(vista)
        def envoltorio(request, *args, **kwargs):
            # Si no hay sesión activa, redirige al login guardando la página destino
            if not request.session.get("logueado"):
                login_url = reverse("sena:login")
                return redirect(f"{login_url}?next={request.path_info}")
            
            # Verifica que el usuario de la sesión exista y esté activo
            from sena.models import Usuario
            usuario = Usuario.objects.filter(id=request.session["logueado"]["id"], activo=True).first()
            if usuario is None:
                del request.session["logueado"]
                return redirect("sena:login")
            
            # Si se indicaron roles, comprueba que el rol del usuario esté permitido
            if roles:
                rol = request.session["logueado"]["rol"]
                if rol not in roles:
                    return redirect("sena:login")
            
            return vista(request, *args, **kwargs)
        return envoltorio
    return decorador
