from datetime import date, time, timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from .models import HorarioTrabajo, Notificacion, Peluqueria, Usuario
from .serializers import ReservaSerializer
from .views import cita_disponible


class TecnoCorteTests(TestCase):
    def setUp(self):
        self.cliente = Usuario.objects.create(
            nombre="Cliente", apellido="Prueba", email="cliente@test.com",
            password=make_password("cliente123"), rol="Cliente"
        )
        self.barbero = Usuario.objects.create(
            nombre="Barbero", apellido="Prueba", email="barbero@test.com",
            password=make_password("barbero123"), rol="Barbero"
        )
        self.peluqueria = Peluqueria.objects.create(
            nombre="Barbería Test", ubicacion="Centro", telefono="3000000"
        )
        HorarioTrabajo.objects.create(
            peluqueria=self.peluqueria, dia_semana=0, activo=True,
            hora_inicio=time(9), hora_fin=time(18)
        )

    def iniciar_sesion(self, usuario):
        session = self.client.session
        session["logueado"] = {"id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol}
        session.save()

    def test_inicio_muestra_inicio_al_cliente_logueado(self):
        self.iniciar_sesion(self.cliente)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "publicos/index.html")

    def test_login_usa_password_hasheada(self):
        response = self.client.post(reverse("sena:login"), {
            "user": self.cliente.email,
            "password": "cliente123",
            "rol": "Cliente",
        })
        self.assertRedirects(response, reverse("sena:inicio"))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_registro_envia_correo_con_diseno_html(self):
        response = self.client.post(reverse("sena:registro"), {
            "nombre": "Nuevo",
            "apellido": "Cliente",
            "email": "nuevo@test.com",
            "telefono": "3000000",
            "password": "Cliente123!",
        })

        self.assertRedirects(response, reverse("sena:inicio"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].alternatives), 1)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("background:#090909", html)
        self.assertIn("cid:tecnocorte-logo", html)
        self.assertEqual(mail.outbox[0].attachments[0].get("Content-ID"), "<tecnocorte-logo>")

    def test_no_permite_reservar_fecha_pasada(self):
        lunes_pasado = date.today() - timedelta(days=date.today().weekday() + 7)
        disponible, mensaje = cita_disponible(
            lunes_pasado.isoformat(), "10:00", self.peluqueria.id, "Corte de Cabello"
        )
        self.assertFalse(disponible)
        self.assertIn("pasada", mensaje)

    def test_cliente_no_entra_a_panel_admin(self):
        self.iniciar_sesion(self.cliente)
        response = self.client.get(reverse("sena:admin_dashboard"))
        self.assertRedirects(response, reverse("sena:login"))

    def test_cambio_password_usa_la_cuenta_de_la_sesion(self):
        self.iniciar_sesion(self.cliente)
        response = self.client.get(reverse("sena:cambiar_password"))

        self.assertContains(response, self.cliente.email)
        response = self.client.post(reverse("sena:cambiar_password"), {
            "password_actual": "cliente123",
            "password": "ClienteNueva123!",
            "password_confirm": "ClienteNueva123!",
        })

        self.assertRedirects(response, reverse("sena:usuario_perfil"))
        self.cliente.refresh_from_db()
        self.assertTrue(check_password("ClienteNueva123!", self.cliente.password))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", CONTACT_EMAIL="tecnocorte083@gmail.com")
    def test_mensaje_de_ayuda_llega_al_correo_oficial_y_al_panel(self):
        admin = Usuario.objects.create(
            nombre="Admin", apellido="Prueba", email="admin@test.com",
            password=make_password("admin123"), rol="Admin"
        )
        response = self.client.post(reverse("sena:ayuda"), {
            "nombre": "Visitante",
            "email": "visitante@test.com",
            "asunto": "Consulta de horarios",
            "mensaje": "¿Qué horarios tienen disponibles?",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mail.outbox[0].to, ["tecnocorte083@gmail.com"])
        self.assertIn("Consulta de horarios", mail.outbox[0].subject)
        self.assertTrue(Notificacion.objects.filter(usuario=admin, mensaje__contains="Consulta de horarios").exists())

    def test_serializer_incluye_y_valida_servicio(self):
        serializer = ReservaSerializer(data={
            "cliente": self.cliente.id,
            "peluquero": self.barbero.id,
            "peluqueria": self.peluqueria.id,
            "fecha": "2099-01-03",
            "hora": "10:00",
            "servicio": "Servicio inexistente",
            "estado": "Pendiente",
        })
        self.assertIn("servicio", serializer.fields)
        self.assertFalse(serializer.is_valid())
