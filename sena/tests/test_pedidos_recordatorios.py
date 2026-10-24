from datetime import date, timedelta

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.hashers import make_password

from ..models import HorarioTrabajo, Pedido, Peluqueria, RegistroAccion, Reserva, Usuario


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SITE_URL="https://tecnocorte.test")
class PedidosYRecordatoriosTests(TestCase):
    def setUp(self):
        self.cliente = Usuario.objects.create(
            nombre="Ana", apellido="Cliente", email="ana@test.com",
            password=make_password("ClaveSegura1!"), rol="Cliente",
        )
        self.admin = Usuario.objects.create(
            nombre="Admin", apellido="Principal", email="admin@test.com",
            password=make_password("ClaveSegura1!"), rol="Admin",
        )
        self.peluqueria = Peluqueria.objects.create(
            nombre="Sede Central", ubicacion="Calle 1", telefono="3000000000",
        )
        self.barbero = Usuario.objects.create(
            nombre="Luis", apellido="Barbero", email="luis@test.com",
            password=make_password("ClaveSegura1!"), rol="Barbero",
            peluqueria=self.peluqueria,
        )

    def iniciar(self, usuario):
        self.client.session["logueado"] = {
            "id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol,
            "sesion_version": usuario.sesion_version,
        }
        self.client.session.save()

    def test_recordatorio_por_correo_se_envia_una_sola_vez(self):
        momento = timezone.localtime() + timedelta(hours=2)
        Reserva.objects.create(
            cliente=self.cliente, peluquero=self.barbero, peluqueria=self.peluqueria,
            fecha=momento.date(), hora=momento.time().replace(second=0, microsecond=0),
            servicio="Corte de Cabello", estado="Confirmada",
        )

        call_command("enviar_recordatorios")
        self.assertEqual(len(mail.outbox), 1)
        reserva = Reserva.objects.get()
        self.assertIsNotNone(reserva.recordatorio_correo_enviado)

        call_command("enviar_recordatorios")
        self.assertEqual(len(mail.outbox), 1)

    def test_admin_completa_pedido_al_entregarlo_y_confirmar_pago(self):
        pedido = Pedido.objects.create(cliente=self.cliente, total=40000)
        self.client.post(
            reverse("sena:login"),
            {"user": self.admin.email, "password": "ClaveSegura1!"},
        )

        response = self.client.post(
            reverse("sena:admin_actualizar_pedido", args=[pedido.id]),
            {"estado": "Entregado", "pago_confirmado": "on"},
        )

        self.assertRedirects(response, reverse("sena:admin_pedidos"))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "Completado")
        self.assertTrue(pedido.pago_confirmado)
        self.assertIsNotNone(pedido.fecha_pago)
        self.assertIsNotNone(pedido.fecha_entrega)
        self.assertTrue(RegistroAccion.objects.filter(accion="actualizar_pedido", entidad_id=pedido.id).exists())

    def test_pedido_entregado_se_completa_al_confirmar_pago_despues(self):
        pedido = Pedido.objects.create(cliente=self.cliente, total=40000)
        self.client.post(
            reverse("sena:login"),
            {"user": self.admin.email, "password": "ClaveSegura1!"},
        )

        self.client.post(
            reverse("sena:admin_actualizar_pedido", args=[pedido.id]),
            {"estado": "Entregado"},
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "Entregado")
        self.assertFalse(pedido.pago_confirmado)

        self.client.post(
            reverse("sena:admin_actualizar_pedido", args=[pedido.id]),
            {"estado": "Entregado", "pago_confirmado": "on"},
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "Completado")
        self.assertTrue(pedido.pago_confirmado)

    def test_pedido_completado_no_muestra_controles_ni_admite_cambios(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente, total=40000, estado="Completado",
            pago_confirmado=True, fecha_pago=timezone.now(), fecha_entrega=timezone.now(),
        )
        self.client.post(
            reverse("sena:login"),
            {"user": self.admin.email, "password": "ClaveSegura1!"},
        )

        respuesta = self.client.get(reverse("sena:admin_pedidos"))
        self.assertContains(respuesta, "Pedido completado")
        self.assertNotContains(respuesta, f'name="estado"')
        self.assertNotContains(respuesta, f'name="pago_confirmado"')

        self.client.post(
            reverse("sena:admin_actualizar_pedido", args=[pedido.id]),
            {"estado": "Pendiente"},
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "Completado")
        self.assertTrue(pedido.pago_confirmado)

    def test_cliente_puede_confirmar_una_reserva_desde_la_vista(self):
        # Cubre el flujo completo que usa la pantalla: preconfirmar y luego
        # confirmar con los mismos campos ocultos del segundo formulario.
        fecha = date(2030, 1, 10)  # jueves
        HorarioTrabajo.objects.create(
            peluqueria=self.peluqueria, dia_semana=fecha.weekday(),
            activo=True, hora_inicio="09:00", hora_fin="18:00",
        )
        self.client.post(
            reverse("sena:login"),
            {"user": self.cliente.email, "password": "ClaveSegura1!"},
        )
        datos = {
            "servicio": "Corte de Cabello", "peluquero": self.barbero.id,
            "peluqueria": self.peluqueria.id, "fecha": fecha.isoformat(), "hora": "10:00",
        }

        previa = self.client.post(reverse("sena:usuario_pre_confirmar"), datos)
        self.assertEqual(previa.status_code, 200)
        confirmacion = self.client.post(reverse("sena:usuario_confirmar_reserva"), datos)

        self.assertRedirects(confirmacion, reverse("sena:inicio"))
        self.assertTrue(Reserva.objects.filter(cliente=self.cliente, fecha=fecha).exists())

    def test_cambiar_version_invalida_una_sesion_anterior(self):
        self.iniciar(self.cliente)
        self.cliente.sesion_version += 1
        self.cliente.save(update_fields=["sesion_version"])

        response = self.client.get(reverse("sena:usuario_perfil"))

        self.assertEqual(response.url, reverse("sena:login") + "?next=/usuario/perfil/")

    def test_no_permite_reabrir_una_cita_completada_desde_el_panel(self):
        from datetime import date

        cita = Reserva.objects.create(
            cliente=self.cliente, peluquero=self.barbero, peluqueria=self.peluqueria,
            fecha=date(2030, 1, 10), hora="10:00", servicio="Corte de Cabello",
            estado="Completada",
        )
        self.client.post(
            reverse("sena:login"),
            {"user": self.barbero.email, "password": "ClaveSegura1!"},
        )

        response = self.client.post(
            reverse("sena:peluquero_cambiar_estado", args=[cita.id]),
            {"estado": "Pendiente"},
        )

        self.assertRedirects(response, reverse("sena:peluquero_dashboard"))
        cita.refresh_from_db()
        self.assertEqual(cita.estado, "Completada")
