# Script de datos de prueba: crea peluquerías, usuarios y productos de ejemplo
# Se ejecuta por separado con: python crear_datos.py
import os, django
# Configura el entorno de Django para poder usar los modelos fuera del servidor
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tecnocorte.settings')
django.setup()
from sena.models import Usuario, Peluqueria, Producto
from django.contrib.auth.hashers import make_password

# Bloque: creación de las peluquerías (sedes) de prueba
print("=" * 60)
print("CREANDO PELUQUERÍAS")
print("=" * 60)
Peluqueria.objects.get_or_create(nombre="Barbería Itagüí", defaults={"ubicacion": "Calle 10", "telefono": "300-111"})
Peluqueria.objects.get_or_create(nombre="Barbería Centro", defaults={"ubicacion": "Carrera 45", "telefono": "300-222"})
print(" Peluquerías creadas")

print("\n" + "=" * 60)
print("CREANDO USUARIOS DE PRUEBA")
print("=" * 60)

# ADMINISTRADORES
print("\n ADMINISTRADORES:")
admin_users = [
    {"email": "admin@test.com", "nombre": "Admin", "apellido": "Test", "password": "admin123", "telefono": "300-0000"},
    {"email": "administrador@tecnocorte.com", "nombre": "Daniel", "apellido": "García", "password": "admin123", "telefono": "300-1234"},
]
# Recorre la lista y crea cada administrador si no existe (con contraseña cifrada)
for user_data in admin_users:
    user, created = Usuario.objects.get_or_create(
        email=user_data["email"],
        defaults={
            "nombre": user_data["nombre"],
            "apellido": user_data["apellido"],
            "password": make_password(user_data["password"]),
            "telefono": user_data["telefono"],
            "rol": "Admin"
        }
    )
    status = " Creado" if created else " Existente"
    print(f"  {status}: {user_data['email']} / {user_data['password']}")

# BARBEROS
print("\n BARBEROS:")
barber_users = [
    {"email": "barbero1@test.com", "nombre": "Juan", "apellido": "García", "password": "barbero123", "telefono": "300-2000"},
    {"email": "barbero2@test.com", "nombre": "Carlos", "apellido": "López", "password": "barbero123", "telefono": "300-2001"},
    {"email": "barbero3@test.com", "nombre": "Miguel", "apellido": "Rodríguez", "password": "barbero123", "telefono": "300-2002"},
]
# Recorre la lista y crea cada barbero si no existe
for user_data in barber_users:
    user, created = Usuario.objects.get_or_create(
        email=user_data["email"],
        defaults={
            "nombre": user_data["nombre"],
            "apellido": user_data["apellido"],
            "password": make_password(user_data["password"]),
            "telefono": user_data["telefono"],
            "rol": "Barbero"
        }
    )
    status = " Creado" if created else " Existente"
    print(f"  {status}: {user_data['email']} / {user_data['password']}")

# CLIENTES
print("\n CLIENTES:")
client_users = [
    {"email": "cliente@test.com", "nombre": "Usuario", "apellido": "Prueba", "password": "cliente123", "telefono": "300-3000"},
    {"email": "juan@example.com", "nombre": "Juan", "apellido": "Pérez", "password": "cliente123", "telefono": "300-3001"},
    {"email": "maria@example.com", "nombre": "María", "apellido": "González", "password": "cliente123", "telefono": "300-3002"},
]
# Recorre la lista y crea cada cliente si no existe
for user_data in client_users:
    user, created = Usuario.objects.get_or_create(
        email=user_data["email"],
        defaults={
            "nombre": user_data["nombre"],
            "apellido": user_data["apellido"],
            "password": make_password(user_data["password"]),
            "telefono": user_data["telefono"],
            "rol": "Cliente"
        }
    )
    status = " Creado" if created else " Existente"
    print(f"  {status}: {user_data['email']} / {user_data['password']}")

# Bloque: creación de los productos de la tienda de prueba
print("\n" + "=" * 60)
print("CREANDO PRODUCTOS")
print("=" * 60)
Producto.objects.get_or_create(nombre="Máquina de Cortar", defaults={
    "descripcion": "Máquina profesional para corte de cabello.",
    "precio": 320000, "categoria": "Herramientas",
    "stock": 5, "disponible": True,
    "imagen": "maquina_motilar.jpg",
})
Producto.objects.get_or_create(nombre="Pomada para Cabello", defaults={
    "descripcion": "Pomada con fijación fuerte y acabado mate.",
    "precio": 62000, "categoria": "Fijacion",
    "stock": 10, "disponible": True,
    "imagen": "pomada_barba.jpeg",
})
Producto.objects.get_or_create(nombre="Cepillo para Cabello", defaults={
    "descripcion": "Cepillo de cerdas naturales para peinar.",
    "precio": 45000, "categoria": "Herramientas",
    "stock": 8, "disponible": True,
    "imagen": "cepillo.jpeg",
})
Producto.objects.get_or_create(nombre='Tijeras Profesionales', defaults={
    "descripcion": "Tijeras de acero para corte de precisión.",
    "precio": 180000, "categoria": "Herramientas",
    "stock": 1, "disponible": True,
    "imagen": "Tijeras.jpeg",
})
print(" Productos creados")

# Bloque final: resumen en consola con las credenciales de acceso creadas
print("\n" + "=" * 60)
print(" ¡DATOS DE PRUEBA CREADOS EXITOSAMENTE!")
print("=" * 60)
print("\n CREDENCIALES DISPONIBLES:")
print("\n ADMINISTRADOR:")
print("   Email: admin@test.com")
print("   Contraseña: admin123")
print("\n PELUQUERO:")
print("   Email: barbero1@test.com")
print("   Contraseña: barbero123")
print("\n CLIENTE:")
print("   Email: cliente@test.com")
print("   Contraseña: cliente123")
print("\n" + "=" * 60)


