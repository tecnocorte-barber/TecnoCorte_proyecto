from datetime import date, time

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from rest_framework.test import APIClient

from ..models import HorarioTrabajo, Peluqueria, Producto, Reserva, Usuario


class APIPermisosTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.cliente = Usuario.objects.create(
            nombre="Cliente", apellido="API", email="cliente.api@test.com",
            password=make_password("ClaveSegura1!"), rol="Cliente",
        )
        self.admin = Usuario.objects.create(
            nombre="Admin", apellido="API", email="admin.api@test.com",
            password=make_password("ClaveSegura1!"), rol="Admin",
        )
        self.peluqueria = Peluqueria.objects.create(
            nombre="Sede API", ubicacion="Centro", telefono="3000000000",
        )

    def autenticar(self, usuario):
        respuesta = self.api.post("/api/auth/token/", {
            "email": usuario.email, "password": "ClaveSegura1!",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.json()['access']}")

    def test_api_rechaza_peticion_sin_autenticacion(self):
        respuesta = self.api.get("/api/productos/")
        self.assertEqual(respuesta.status_code, 401)

    def test_cliente_puede_consultar_productos(self):
        Producto.objects.create(nombre="Producto API", precio=1000, stock=5, disponible=True)
        self.autenticar(self.cliente)
        respuesta = self.api.get("/api/productos/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.json()), 1)

    def test_cliente_no_puede_crear_productos(self):
        self.autenticar(self.cliente)
        respuesta = self.api.post("/api/productos/", {
            "nombre": "No permitido", "precio": 1000, "stock": 5,
            "categoria": "Herramientas", "disponible": True,
        }, format="json")
        self.assertEqual(respuesta.status_code, 403)

    def test_admin_puede_crear_producto(self):
        self.autenticar(self.admin)
        respuesta = self.api.post("/api/productos/", {
            "nombre": "Producto administrador", "descripcion": "Prueba",
            "precio": 1000, "stock": 5, "categoria": "Herramientas", "disponible": True,
        }, format="json")
        self.assertEqual(respuesta.status_code, 201)
        self.assertTrue(Producto.objects.filter(nombre="Producto administrador").exists())

    def test_cliente_solo_ve_sus_reservas(self):
        barbero = Usuario.objects.create(
            nombre="Barbero", apellido="API", email="barbero.api@test.com",
            password=make_password("ClaveSegura1!"), rol="Barbero", peluqueria=self.peluqueria,
        )
        HorarioTrabajo.objects.create(
            peluqueria=self.peluqueria, dia_semana=0, activo=True,
            hora_inicio=time(9), hora_fin=time(18),
        )
        otra = Usuario.objects.create(
            nombre="Otro", apellido="Cliente", email="otro.api@test.com",
            password=make_password("ClaveSegura1!"), rol="Cliente",
        )
        Reserva.objects.create(
            cliente=self.cliente, peluquero=barbero, peluqueria=self.peluqueria,
            fecha=date(2030, 1, 7), hora=time(10), servicio="Corte de Cabello",
        )
        Reserva.objects.create(
            cliente=otra, peluquero=barbero, peluqueria=self.peluqueria,
            fecha=date(2030, 1, 8), hora=time(10), servicio="Corte de Cabello",
        )
        self.autenticar(self.cliente)
        respuesta = self.api.get("/api/reservas/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.json()), 1)
        self.assertEqual(respuesta.json()[0]["cliente"], self.cliente.id)
