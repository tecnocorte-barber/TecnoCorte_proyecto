import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tecnocorte.settings')
django.setup()
from sena.models import Usuario, Peluqueria, Producto

Peluqueria.objects.get_or_create(nombre="Barbería Itagüí", defaults={"ubicacion": "Calle 10", "telefono": "300-111"})
Peluqueria.objects.get_or_create(nombre="Barbería Centro", defaults={"ubicacion": "Carrera 45", "telefono": "300-222"})

Usuario.objects.get_or_create(email="admin@test.com", defaults={"nombre": "Admin", "apellido": "Test", "password": "admin123", "rol": "Admin"})
Usuario.objects.get_or_create(email="peluquero1@test.com", defaults={"nombre": "Juan", "apellido": "García", "password": "peluquero123", "rol": "Peluquero"})
Usuario.objects.get_or_create(email="peluquero2@test.com", defaults={"nombre": "Carlos", "apellido": "López", "password": "peluquero123", "rol": "Peluquero"})
Usuario.objects.get_or_create(email="cliente@test.com", defaults={"nombre": "Usuario", "apellido": "Prueba", "password": "cliente123", "rol": "Cliente"})

Producto.objects.get_or_create(nombre="Máquina de Cortar", defaults={
    "descripcion": "Máquina profesional para corte de cabello.",
    "precio": 320000, "categoria": "Herramientas",
    "stock": 5, "disponible": True,
})
Producto.objects.get_or_create(nombre="Pomada para Cabello", defaults={
    "descripcion": "Pomada con fijación fuerte y acabado mate.",
    "precio": 62000, "categoria": "Fijacion",
    "stock": 10, "disponible": True,
})
Producto.objects.get_or_create(nombre="Cepillo para Cabello", defaults={
    "descripcion": "Cepillo de cerdas naturales para peinar.",
    "precio": 45000, "categoria": "Herramientas",
    "stock": 8, "disponible": True,
})
Producto.objects.get_or_create(nombre='Tijeras Profesionales', defaults={
    "descripcion": "Tijeras de acero para corte de precisión.",
    "precio": 180000, "categoria": "Herramientas",
    "stock": 0, "disponible": False,
})

print("✅ Datos creados\nadmin@test.com / admin123\npeluquero1@test.com / peluquero123\ncliente@test.com / cliente123")

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
for user in User.objects.all():
    token, created = Token.objects.get_or_create(user=user)
    print(f"Token para {user.username}: {token.key}")
