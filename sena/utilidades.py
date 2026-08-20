from django.shortcuts import redirect
from django.urls import reverse
from functools import wraps

def autorizacion(roles=[]):
    def decorador(vista):
        @wraps(vista)
        def envoltorio(request, *args, **kwargs):
            if not request.session.get("logueado"):
                # Redirigir a login con el parámetro next para volver después
                login_url = reverse("sena:login")
                return redirect(f"{login_url}?next={request.path_info}")
            
            if roles:
                rol = request.session["logueado"]["rol"]
                if rol not in roles:
                    return redirect("sena:login")
            
            return vista(request, *args, **kwargs)
        return envoltorio
    return decorador
