import re
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.hashers import check_password
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from ..models import RegistroPendiente, Usuario


@override_settings(REQUIRE_EMAIL_VERIFICATION=True)
class VerificacionRegistroTests(TestCase):
    datos = {
        "nombre": "Ana",
        "apellido": "Prueba",
        "email": "ana.verificacion@example.com",
        "telefono": "3001234567",
        "password": "Segura123!",
    }

    def iniciar_registro(self):
        respuesta = self.client.post(reverse("sena:registro"), self.datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Usuario.objects.filter(email=self.datos["email"]).exists())
        pendiente = RegistroPendiente.objects.get(email=self.datos["email"])
        return respuesta, pendiente

    def test_codigo_verifica_y_crea_la_cuenta_solo_al_confirmar(self):
        respuesta, pendiente = self.iniciar_registro()
        self.assertEqual(len(mail.outbox), 1)
        codigo = re.search(r"(?<!\d)\d{6}(?!\d)", mail.outbox[0].body).group()

        respuesta = self.client.post(reverse("sena:verificar_correo"), {
            "token": respuesta.context["token"], "codigo": codigo,
        })

        self.assertRedirects(respuesta, reverse("sena:inicio"))
        usuario = Usuario.objects.get(email=self.datos["email"])
        self.assertTrue(usuario.email_verificado)
        self.assertTrue(check_password(self.datos["password"], usuario.password))
        self.assertFalse(RegistroPendiente.objects.filter(pk=pendiente.pk).exists())
        self.assertEqual(self.client.session["logueado"]["id"], usuario.id)

    def test_enlace_funciona_sin_la_sesion_que_inicio_el_registro(self):
        self.iniciar_registro()
        contenido_html = mail.outbox[0].alternatives[0][0]
        enlace = re.search(r'href="(https?://[^\"]+)"', contenido_html).group(1)
        partes = urlsplit(enlace)
        token = parse_qs(partes.query)["token"][0]
        otro_navegador = self.client.__class__()

        respuesta = otro_navegador.get(partes.path, {"token": token})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Confirmar y verificar mi correo")
        self.assertFalse(Usuario.objects.filter(email=self.datos["email"]).exists())

        respuesta = otro_navegador.post(reverse("sena:verificar_correo"), {
            "token": token, "confirmar_enlace": "1",
        })
        self.assertRedirects(respuesta, reverse("sena:inicio"))
        self.assertTrue(Usuario.objects.get(email=self.datos["email"]).email_verificado)

    def test_reenvio_emite_codigo_y_enlace_nuevos(self):
        respuesta, _ = self.iniciar_registro()
        token_anterior = respuesta.context["token"]
        codigo_anterior = re.search(r"(?<!\d)\d{6}(?!\d)", mail.outbox[0].body).group()

        respuesta = self.client.post(reverse("sena:reenviar_verificacion"), {
            "token": token_anterior,
        })
        self.assertTrue(respuesta.context["enviado"])
        self.assertEqual(len(mail.outbox), 2)
        token_nuevo = respuesta.context["token"]
        self.assertNotEqual(token_anterior, token_nuevo)

        respuesta = self.client.post(reverse("sena:verificar_correo"), {
            "token": token_nuevo, "codigo": codigo_anterior,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El código no es válido o ya expiró")
        self.assertFalse(Usuario.objects.filter(email=self.datos["email"]).exists())

        codigo_nuevo = re.search(r"(?<!\d)\d{6}(?!\d)", mail.outbox[1].body).group()
        respuesta = self.client.post(reverse("sena:verificar_correo"), {
            "token": token_nuevo, "codigo": codigo_nuevo,
        })
        self.assertRedirects(respuesta, reverse("sena:inicio"))
        self.assertTrue(Usuario.objects.filter(email=self.datos["email"]).exists())

    def test_codigo_dura_quince_minutos_exactos(self):
        respuesta, pendiente = self.iniciar_registro()
        codigo = re.search(r"(?<!\d)\d{6}(?!\d)", mail.outbox[0].body).group()
        emitido = pendiente.codigo_expira - timedelta(minutes=15)

        with patch("sena.views.autenticacion.timezone.now", return_value=emitido + timedelta(minutes=14, seconds=59)):
            respuesta = self.client.post(reverse("sena:verificar_correo"), {
                "token": respuesta.context["token"], "codigo": codigo,
            })
        self.assertRedirects(respuesta, reverse("sena:inicio"))

    def test_codigo_expira_al_cumplir_quince_minutos(self):
        respuesta, pendiente = self.iniciar_registro()
        codigo = re.search(r"(?<!\d)\d{6}(?!\d)", mail.outbox[0].body).group()
        emitido = pendiente.codigo_expira - timedelta(minutes=15)

        with patch("sena.views.autenticacion.timezone.now", return_value=emitido + timedelta(minutes=15)):
            respuesta = self.client.post(reverse("sena:verificar_correo"), {
                "token": respuesta.context["token"], "codigo": codigo,
            })
        self.assertContains(respuesta, "El código no es válido o ya expiró")
        self.assertFalse(Usuario.objects.filter(email=self.datos["email"]).exists())

    def test_login_no_permite_entrar_a_una_cuenta_sin_verificar(self):
        from django.contrib.auth.hashers import make_password

        usuario = Usuario.objects.create(
            nombre="Pendiente", apellido="Prueba", email="pendiente@example.com",
            password=make_password("Segura123!"), email_verificado=False,
        )
        respuesta = self.client.post(reverse("sena:login"), {
            "user": usuario.email, "password": "Segura123!",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Verifica tu correo antes de iniciar sesión")
        self.assertNotIn("logueado", self.client.session)
