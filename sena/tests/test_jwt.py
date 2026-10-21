from django.contrib.auth.hashers import make_password
from django.test import TestCase
from rest_framework.test import APIClient

from ..models import RegistroAccion, Usuario


class JWTAuthenticationTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create(
            nombre="Cliente", apellido="JWT", email="jwt@test.com",
            password=make_password("ClaveSegura1!"), rol="Cliente",
        )
        self.client_api = APIClient()

    def obtener_tokens(self):
        respuesta = self.client_api.post("/api/auth/token/", {
            "email": self.usuario.email,
            "password": "ClaveSegura1!",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.json()

    def test_emite_access_y_refresh_token(self):
        tokens = self.obtener_tokens()
        self.assertTrue(tokens["access"])
        self.assertTrue(tokens["refresh"])

    def test_logout_invalida_el_token_y_audita_el_usuario(self):
        tokens = self.obtener_tokens()
        self.client_api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        respuesta = self.client_api.post("/api/auth/logout/", {}, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(RegistroAccion.objects.filter(
            actor=self.usuario, accion="cierre_sesiones_jwt"
        ).exists())

        respuesta = self.client_api.get("/api/productos/")
        self.assertEqual(respuesta.status_code, 401)

    def test_refresh_token_entrega_un_nuevo_access_token(self):
        tokens = self.obtener_tokens()
        respuesta = self.client_api.post("/api/auth/refresh/", {
            "refresh": tokens["refresh"],
        }, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["access"])

        reutilizado = self.client_api.post("/api/auth/refresh/", {
            "refresh": tokens["refresh"],
        }, format="json")
        self.assertEqual(reutilizado.status_code, 401)
