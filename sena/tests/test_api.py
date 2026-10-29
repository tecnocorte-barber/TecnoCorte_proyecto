from datetime import date, time

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from rest_framework.test import APIClient

from ..models import (
    HorarioTrabajo, Pedido, PedidoProducto, Peluqueria, Producto, Reserva,
    Usuario,
)


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

    def test_api_admin_no_puede_crear_reserva_cancelada(self):
        barbero = Usuario.objects.create(
            nombre="Barbero", apellido="API", email="barbero.estado@test.com",
            password=make_password("ClaveSegura1!"), rol="Barbero",
            peluqueria=self.peluqueria,
        )
        fecha = date(2030, 1, 10)
        HorarioTrabajo.objects.create(
            peluqueria=self.peluqueria, dia_semana=fecha.weekday(),
            activo=True, hora_inicio=time(9), hora_fin=time(18),
        )
        self.autenticar(self.admin)

        respuesta = self.api.post("/api/reservas/", {
            "cliente": self.cliente.id,
            "peluquero": barbero.id,
            "peluqueria": self.peluqueria.id,
            "fecha": fecha.isoformat(),
            "hora": "10:00",
            "servicio": "Corte de Cabello",
            "estado": "Cancelada",
        }, format="json")

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Reserva.objects.exists())

    def test_api_cancelar_pedido_devuelve_los_productos_al_stock(self):
        producto = Producto.objects.create(
            nombre="Producto pedido", precio=1000, stock=0, disponible=False,
        )
        pedido = Pedido.objects.create(
            cliente=self.cliente, total=2000, estado="Pendiente",
        )
        PedidoProducto.objects.create(
            pedido=pedido, producto=producto, cantidad=2, precio=1000,
        )
        self.autenticar(self.admin)

        respuesta = self.api.patch(
            f"/api/pedidos/{pedido.id}/",
            {"estado": "Cancelado"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200)
        pedido.refresh_from_db()
        producto.refresh_from_db()
        self.assertEqual(pedido.estado, "Cancelado")
        self.assertEqual(producto.stock, 2)
        self.assertTrue(producto.disponible)

    def test_api_no_elimina_pedidos_antes_de_reponer_el_inventario(self):
        pedido = Pedido.objects.create(cliente=self.cliente, total=1000)
        self.autenticar(self.admin)

        respuesta = self.api.delete(f"/api/pedidos/{pedido.id}/")

        self.assertEqual(respuesta.status_code, 403)
        self.assertTrue(Pedido.objects.filter(id=pedido.id).exists())

    def test_api_no_crea_pedidos_fuera_del_checkout(self):
        self.autenticar(self.admin)

        respuesta = self.api.post("/api/pedidos/", {}, format="json")

        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Pedido.objects.exists())

    def test_api_no_modifica_detalles_de_pedido_sin_actualizar_inventario(self):
        producto = Producto.objects.create(
            nombre="Producto pedido", precio=1000, stock=5, disponible=True,
        )
        pedido = Pedido.objects.create(cliente=self.cliente, total=1000)
        detalle = PedidoProducto.objects.create(
            pedido=pedido, producto=producto, cantidad=1, precio=1000,
        )
        self.autenticar(self.admin)

        crear = self.api.post("/api/pedido-productos/", {
            "pedido": pedido.id, "producto": producto.id,
            "cantidad": 2, "precio": 1000,
        }, format="json")
        actualizar = self.api.patch(
            f"/api/pedido-productos/{detalle.id}/",
            {"cantidad": 3},
            format="json",
        )
        eliminar = self.api.delete(f"/api/pedido-productos/{detalle.id}/")

        self.assertEqual(crear.status_code, 405)
        self.assertEqual(actualizar.status_code, 405)
        self.assertEqual(eliminar.status_code, 405)
        producto.refresh_from_db()
        detalle.refresh_from_db()
        self.assertEqual(producto.stock, 5)
        self.assertEqual(detalle.cantidad, 1)

    def test_api_no_puede_reabrir_una_reserva_cancelada(self):
        barbero = Usuario.objects.create(
            nombre="Barbero", apellido="API", email="barbero.reabrir@test.com",
            password=make_password("ClaveSegura1!"), rol="Barbero",
            peluqueria=self.peluqueria,
        )
        cita = Reserva.objects.create(
            cliente=self.cliente, peluquero=barbero,
            peluqueria=self.peluqueria, fecha=date(2030, 1, 10),
            hora=time(10), estado="Cancelada",
        )
        self.autenticar(self.admin)

        respuesta = self.api.patch(
            f"/api/reservas/{cita.id}/",
            {"estado": "Pendiente"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, "Cancelada")
