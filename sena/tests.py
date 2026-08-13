from django.test import TestCase


class InicioViewTests(TestCase):
    def test_inicio_muestra_la_pagina_publica_even_when_logged_in(self):
        session = self.client.session
        session['logueado'] = {'id': 1, 'nombre': 'Cliente', 'rol': 'Cliente'}
        session.save()

        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'index.html')
