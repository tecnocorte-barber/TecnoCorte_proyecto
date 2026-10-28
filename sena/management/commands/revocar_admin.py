from django.core.management.base import BaseCommand, CommandError
from sena.models import Usuario

class Command(BaseCommand):
    help = "Revoca privilegios administrativos y deja una cuenta como Cliente."
    def add_arguments(self, parser):
        parser.add_argument("email")
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        usuario = Usuario.objects.filter(email__iexact=email).first()
        if not usuario:
            raise CommandError("Cuenta no encontrada")
        usuario.rol = "Cliente"
        usuario.peluqueria = None
        usuario.sesion_version += 1
        usuario.save(update_fields=["rol", "peluqueria", "sesion_version"])
        self.stdout.write(self.style.SUCCESS(f"{email} degradado a Cliente"))
