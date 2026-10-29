from django.test import TestCase
from django.urls import reverse

from ..models import Notificacion, Peluqueria, Usuario


class AdministracionRolesTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create(
            nombre="Ana", apellido="Admin", email="admin@test.com",
            password="hash", rol="Admin",
        )
        self.superadmin = Usuario.objects.create(
            nombre="Sofia", apellido="Super", email="superadmin@test.com",
            password="hash", rol="SuperAdmin",
        )
        self.otro_admin = Usuario.objects.create(
            nombre="Luis", apellido="Admin", email="otro-admin@test.com",
            password="hash", rol="Admin",
        )
        self.cliente = Usuario.objects.create(
            nombre="Carlos", apellido="Cliente", email="cliente@test.com",
            password="hash", rol="Cliente",
        )
        self.peluqueria = Peluqueria.objects.create(
            nombre="Centro", ubicacion="Calle 1", telefono="300-1111",
        )

    def iniciar_sesion(self, usuario):
        session = self.client.session
        session["logueado"] = {
            "id": usuario.id,
            "nombre": usuario.nombre,
            "rol": usuario.rol,
        }
        session.save()

    def test_admin_no_puede_editar_cuentas_admin_ni_superadmin(self):
        self.iniciar_sesion(self.admin)
        url = reverse("sena:admin_editar_usuario", args=[self.otro_admin.id])
        response = self.client.get(url)
        self.assertRedirects(response, reverse("sena:admin_usuarios"))

        response = self.client.post(url, {
            "nombre": "Modificado",
            "apellido": "Admin",
            "rol": "Cliente",
        })
        self.assertRedirects(response, reverse("sena:admin_usuarios"))
        self.otro_admin.refresh_from_db()
        self.assertEqual(self.otro_admin.rol, "Admin")
        self.assertEqual(self.otro_admin.nombre, "Luis")

        response = self.client.get(reverse("sena:admin_usuarios"))
        self.assertNotContains(
            response,
            reverse("sena:admin_editar_usuario", args=[self.otro_admin.id]),
        )
        self.assertNotContains(
            response,
            reverse("sena:admin_editar_usuario", args=[self.superadmin.id]),
        )

    def test_admin_no_puede_asignar_rol_admin_en_post(self):
        self.iniciar_sesion(self.admin)
        response = self.client.get(reverse("sena:admin_crear_usuario"))
        self.assertContains(response, 'value="Cliente"')
        self.assertContains(response, 'value="Barbero"')
        self.assertNotContains(response, 'value="Admin"')
        self.assertNotContains(response, 'value="SuperAdmin"')

        response = self.client.post(reverse("sena:admin_crear_usuario"), {
            "nombre": "Nuevo",
            "apellido": "Admin",
            "email": "nuevo@test.com",
            "password": "Abcdef1!",
            "rol": "Admin",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No tienes permiso para asignar ese rol")
        self.assertFalse(Usuario.objects.filter(email="nuevo@test.com").exists())

    def test_admin_puede_cambiar_un_cliente_a_barbero(self):
        self.iniciar_sesion(self.admin)
        response = self.client.post(
            reverse("sena:admin_editar_usuario", args=[self.cliente.id]),
            {
                "nombre": self.cliente.nombre,
                "apellido": self.cliente.apellido,
                "rol": "Barbero",
                "peluqueria": self.peluqueria.id,
            },
        )
        self.assertRedirects(response, reverse("sena:admin_usuarios"))
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.rol, "Barbero")
        self.assertEqual(self.cliente.peluqueria, self.peluqueria)

    def test_superadmin_puede_cambiar_rol_y_borra_notificaciones_del_usuario(self):
        propia = Notificacion.objects.create(
            usuario=self.otro_admin, mensaje="Notificación antigua",
        )
        Notificacion.objects.create(usuario=self.cliente, mensaje="Aviso ajeno")
        self.iniciar_sesion(self.superadmin)

        response = self.client.get(
            reverse("sena:admin_editar_usuario", args=[self.otro_admin.id])
        )
        self.assertContains(response, 'value="Cliente"')
        self.assertContains(response, 'value="Admin"')
        self.assertNotContains(response, 'value="SuperAdmin"')

        response = self.client.post(
            reverse("sena:admin_editar_usuario", args=[self.otro_admin.id]),
            {
                "nombre": self.otro_admin.nombre,
                "apellido": self.otro_admin.apellido,
                "rol": "Cliente",
            },
        )
        self.assertRedirects(response, reverse("sena:admin_usuarios"))
        self.otro_admin.refresh_from_db()
        self.assertEqual(self.otro_admin.rol, "Cliente")
        self.assertFalse(Notificacion.objects.filter(usuario=self.otro_admin).exists())
        self.assertFalse(Notificacion.objects.filter(id=propia.id).exists())
        self.assertTrue(Notificacion.objects.filter(usuario=self.cliente).exists())

    def test_guardar_sin_cambiar_rol_conserva_notificaciones(self):
        aviso = Notificacion.objects.create(
            usuario=self.cliente, mensaje="Aviso pendiente",
        )
        self.iniciar_sesion(self.superadmin)

        response = self.client.post(
            reverse("sena:admin_editar_usuario", args=[self.cliente.id]),
            {
                "nombre": self.cliente.nombre,
                "apellido": self.cliente.apellido,
                "rol": "Cliente",
            },
        )
        self.assertRedirects(response, reverse("sena:admin_usuarios"))
        self.assertTrue(Notificacion.objects.filter(id=aviso.id).exists())

    def test_superadmin_puede_asignar_rol_admin(self):
        self.iniciar_sesion(self.superadmin)
        response = self.client.post(
            reverse("sena:admin_editar_usuario", args=[self.cliente.id]),
            {
                "nombre": self.cliente.nombre,
                "apellido": self.cliente.apellido,
                "rol": "Admin",
            },
        )
        self.assertRedirects(response, reverse("sena:admin_usuarios"))
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.rol, "Admin")
