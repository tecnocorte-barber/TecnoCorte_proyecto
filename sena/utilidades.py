from django.shortcuts import redirect
from django.urls import reverse
from functools import wraps

def autorizacion(roles=[]):
    def decorador(vista):
        @wraps(vista)
        def envoltorio(request, *args, **kwargs):
            if not request.session.get("logueado"):
                login_url = reverse("sena:login")
                return redirect(f"{login_url}?next={request.path_info}")
            
            from sena.models import Usuario
            usuario = Usuario.objects.filter(id=request.session["logueado"]["id"], activo=True).first()
            if usuario is None:
                del request.session["logueado"]
                return redirect("sena:login")
            
            if roles:
                rol = request.session["logueado"]["rol"]
                if rol not in roles:
                    return redirect("sena:login")
            
            return vista(request, *args, **kwargs)
        return envoltorio
    return decorador
