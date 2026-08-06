from django.shortcuts import redirect
from functools import wraps

def autorizacion(roles=[]):
    def decorador(vista):
        @wraps(vista)
        def envoltorio(request, *args, **kwargs):
            if not request.session.get("logueado"):
                return redirect("sena:login")
            
            if roles:
                rol = request.session["logueado"]["rol"]
                if rol not in roles:
                    return redirect("sena:login")
            
            return vista(request, *args, **kwargs)
        return envoltorio
    return decorador
