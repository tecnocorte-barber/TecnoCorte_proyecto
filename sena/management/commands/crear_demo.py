# Comando TEMPORAL para crear usuarios de prueba (2 clientes, 2 barberos y 1 admin).
# Uso:  python manage.py crear_demo
# Es idempotente: si el usuario ya existe, actualiza sus datos y contraseña.
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password

from sena.models import Usuario, Peluqueria, HorarioTrabajo


# Credenciales de prueba que se muestran en la pantalla de inicio de sesión.
USUARIOS_DEMO = [
    {"email": "admin@tecnocorte.com", "password": "Admin123!", "nombre": "Admin", "apellido": "TecnoCorte", "rol": "Admin"},
    {"email": "cliente1@tecnocorte.com", "password": "Cliente1!", "nombre": "Carlos", "apellido": "Cliente", "rol": "Cliente"},
    {"email": "cliente2@tecnocorte.com", "password": "Cliente2!", "nombre": "Laura", "apellido": "Cliente", "rol": "Cliente"},
    {"email": "barbero1@tecnocorte.com", "password": "Barbero1!", "nombre": "Pedro", "apellido": "Barbero", "rol": "Barbero"},
    {"email": "barbero2@tecnocorte.com", "password": "Barbero2!", "nombre": "Andrés", "apellido": "Barbero", "rol": "Barbero"},
]


class Command(BaseCommand):
    help = "Crea o actualiza usuarios de prueba (2 clientes, 2 barberos y 1 admin)."

    def handle(self, *args, **options):
        # Se necesita una barbería para asociar a los barberos.
        peluqueria = Peluqueria.objects.order_by("id").first()
        if peluqueria is None:
            peluqueria = Peluqueria.objects.create(
                nombre="Barbería Demo",
                ubicacion="Centro, Ciudad Demo",
                telefono="3000000000",
                descripcion="Sede creada por el comando de demostración.",
            )
        # Horario por defecto (lunes a sábado) para poder agendar citas.
        for dia in range(6):
            HorarioTrabajo.objects.get_or_create(
                peluqueria=peluqueria,
                dia_semana=dia,
                defaults={"activo": True, "hora_inicio": "09:00", "hora_fin": "18:00"},
            )

        for datos in USUARIOS_DEMO:
            usuario, creado = Usuario.objects.update_or_create(
                email=datos["email"],
                defaults={
                    "nombre": datos["nombre"],
                    "apellido": datos["apellido"],
                    "password": make_password(datos["password"]),
                    "rol": datos["rol"],
                    "activo": True,
                    "telefono": "3000000000",
                    "peluqueria": peluqueria if datos["rol"] == "Barbero" else None,
                },
            )
            estado = "creado" if creado else "actualizado"
            self.stdout.write(f"{estado}: {usuario.email} ({usuario.rol})")

        self.stdout.write(self.style.SUCCESS("\nUsuarios de prueba listos:"))
        for datos in USUARIOS_DEMO:
            self.stdout.write(f"  {datos['rol']:<8} {datos['email']:<26} {datos['password']}")
