from django.test import TestCase


class InicioViewTests(TestCase):
    def test_inicio_muestra_inicio_al_cliente_logueado(self):
        session = self.client.session
        session['logueado'] = {'id': 1, 'nombre': 'Cliente', 'rol': 'Cliente'}
        session.save()

        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'publicos/index.html')
