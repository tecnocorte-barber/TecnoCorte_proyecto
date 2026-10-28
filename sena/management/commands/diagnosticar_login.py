from django.core.management.base import BaseCommand
from sena.models import Usuario
from django.contrib.auth.hashers import make_password

class Command(BaseCommand):
    help = "Reactiva/verifica una cuenta y opcionalmente cambia su contraseña."
    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--password")
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        usuario = Usuario.objects.filter(email__iexact=email).first()
        if not usuario:
            self.stdout.write(self.style.ERROR("Cuenta no encontrada")); return
        usuario.email = email
        usuario.activo = True
        usuario.email_verificado = True
        if options.get("password"):
            usuario.password = make_password(options["password"])
        usuario.sesion_version += 1
        usuario.save(update_fields=["email", "activo", "email_verificado", "password", "sesion_version"])
        self.stdout.write(self.style.SUCCESS(f"Cuenta reparada: {email}; rol={usuario.rol}"))
