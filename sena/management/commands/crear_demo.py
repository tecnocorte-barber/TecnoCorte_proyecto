# Comando TEMPORAL para crear usuarios de prueba (admin y barberos mostrados en el login).
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
    {"email": "barbero.carlos.itagui@tecnocorte.com", "password": "barbero123", "nombre": "Carlos", "apellido": "Barbero", "rol": "Barbero"},
    {"email": "barbero.juan.centro@tecnocorte.com", "password": "barbero123", "nombre": "Juan", "apellido": "Barbero", "rol": "Barbero"},
    {"email": "barbero.andres.quintero.envigado@tecnocorte.com", "password": "barbero123", "nombre": "Andrés Quintero", "apellido": "Barbero", "rol": "Barbero"},
    {"email": "barbero.miguel.laureles@tecnocorte.com", "password": "barbero123", "nombre": "Miguel", "apellido": "Barbero", "rol": "Barbero"},
    {"email": "barbero.pedro.itagui@tecnocorte.com", "password": "barbero123", "nombre": "Pedro", "apellido": "Barbero", "rol": "Barbero"},
    {"email": "barbero.andres.barbero.itagui@tecnocorte.com", "password": "barbero123", "nombre": "Andrés", "apellido": "Barbero", "rol": "Barbero"},
]


class Command(BaseCommand):
    help = "Crea o actualiza los usuarios de prueba mostrados en el login."

    def handle(self, *args, **options):
        # Peluquerías demo por sede, para que cada barbero quede en la suya.
        sedes_demo = [
            {"clave": "itagui", "nombre": "Barbería Itagüí", "ubicacion": "Calle 10 # 42-15, Itagüí"},
            {"clave": "centro", "nombre": "Barbería Centro", "ubicacion": "Carrera 45 # 20-30, Medellín"},
            {"clave": "envigado", "nombre": "Barbería Envigado", "ubicacion": "Calle 37 Sur # 43-10, Envigado"},
            {"clave": "laureles", "nombre": "Barbería Laureles", "ubicacion": "Carrera 74 # 30-50, Laureles"},
        ]
        sedes = {}
        for sede in sedes_demo:
            peluqueria, _ = Peluqueria.objects.get_or_create(
                nombre=sede["nombre"],
                defaults={"ubicacion": sede["ubicacion"], "telefono": "3000000000"},
            )
            sedes[sede["clave"]] = peluqueria
            for dia in range(6):
                HorarioTrabajo.objects.get_or_create(
                    peluqueria=peluqueria,
                    dia_semana=dia,
                    defaults={"activo": True, "hora_inicio": "09:00", "hora_fin": "18:00"},
                )

        def sede_de_barbero(email):
            email = email.lower()
            for clave in sedes:
                if clave in email:
                    return sedes[clave]
            return sedes["itagui"]

        for datos in USUARIOS_DEMO:
            peluqueria = sede_de_barbero(datos["email"]) if datos["rol"] == "Barbero" else None
            usuario, creado = Usuario.objects.update_or_create(
                email=datos["email"],
                defaults={
                    "nombre": datos["nombre"],
                    "apellido": datos["apellido"],
                    "password": make_password(datos["password"]),
                    "rol": datos["rol"],
                    "activo": True,
                    "telefono": "3000000000",
                    "peluqueria": peluqueria,
                },
            )
            estado = "creado" if creado else "actualizado"
            self.stdout.write(f"{estado}: {usuario.email} ({usuario.rol})")

        self.stdout.write(self.style.SUCCESS("\nUsuarios de prueba listos:"))
        for datos in USUARIOS_DEMO:
            self.stdout.write(f"  {datos['rol']:<8} {datos['email']:<26} {datos['password']}")
