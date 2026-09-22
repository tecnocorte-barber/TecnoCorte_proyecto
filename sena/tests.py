# Tests unitarios de la app sena: verifican login, registro, reservas, permisos y más
from datetime import date, time, timedelta  # Para fechas y horas en las pruebas

from django.contrib.auth.hashers import check_password, make_password  # Para verificar/cifrar contraseñas
from django.core import mail  # Bandeja de correos simulada en tests
from django.test import TestCase  # Clase base para tests de Django
from django.test import override_settings  # Para cambiar configuración temporalmente
from django.urls import reverse  # Para generar URLs por nombre

from .models import HorarioTrabajo, Notificacion, Peluqueria, Usuario  # Modelos usados en tests
from .serializers import ReservaSerializer  # Serializer a probar
from .views import cita_disponible  # Función de verificación de disponibilidad


# Suite principal de tests de TecnoCorte
class TecnoCorteTests(TestCase):
    # Configuración inicial: crea datos de prueba antes de cada test
    def setUp(self):
        self.cliente = Usuario.objects.create(  # Crea un cliente de prueba
            nombre="Cliente", apellido="Prueba", email="cliente@test.com",
            password=make_password("cliente123"), rol="Cliente"
        )
        self.barbero = Usuario.objects.create(  # Crea un barbero de prueba
            nombre="Barbero", apellido="Prueba", email="barbero@test.com",
            password=make_password("barbero123"), rol="Barbero"
        )
        self.peluqueria = Peluqueria.objects.create(  # Crea una peluquería de prueba
            nombre="Barbería Test", ubicacion="Centro", telefono="3000000"
        )
        HorarioTrabajo.objects.create(  # Configura horario de lunes 9am-6pm
            peluqueria=self.peluqueria, dia_semana=0, activo=True,
            hora_inicio=time(9), hora_fin=time(18)
        )

    # Simula inicio de sesión guardando datos en la sesión del cliente de prueba
    def iniciar_sesion(self, usuario):
        session = self.client.session  # Abre la sesión del cliente HTTP
        session["logueado"] = {"id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol}  # Guarda datos de login
        session.save()  # Persiste la sesión

    # Verifica que un cliente logueado ve la página de inicio
    def test_inicio_muestra_inicio_al_cliente_logueado(self):
        self.iniciar_sesion(self.cliente)  # Inicia sesión
        response = self.client.get("/")  # Visita la página principal
        self.assertEqual(response.status_code, 200)  # Debe responder 200 OK
        self.assertTemplateUsed(response, "publicos/index.html")  # Debe usar la plantilla de inicio

    def test_peluquerias_sin_imagen_muestran_logo(self):
        response = self.client.get(reverse("sena:usuario_peluquerias"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "sena/images/Logo.png")

    # Verifica que el login funciona con contraseña hasheada
    def test_login_usa_password_hasheada(self):
        response = self.client.post(reverse("sena:login"), {  # Envía formulario de login
            "user": self.cliente.email,
            "password": "cliente123",
            "rol": "Cliente",
        })
        self.assertRedirects(response, reverse("sena:inicio"))  # Debe redirigir al inicio

    # Verifica que el registro envía un correo con diseño HTML y logo embebido
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_registro_envia_correo_con_diseno_html(self):
        response = self.client.post(reverse("sena:registro"), {  # Envía formulario de registro
            "nombre": "Nuevo",
            "apellido": "Cliente",
            "email": "nuevo@test.com",
            "telefono": "3000000",
            "password": "Cliente123!",
        })

        self.assertRedirects(response, reverse("sena:inicio"))  # Debe redirigir al inicio
        self.assertEqual(len(mail.outbox), 1)  # Debe haber enviado 1 correo
        self.assertEqual(len(mail.outbox[0].alternatives), 1)  # Debe tener versión HTML
        html = mail.outbox[0].alternatives[0][0]  # Extrae el contenido HTML
        self.assertIn("background:#090909", html)  # Verifica estilo del diseño
        self.assertIn("cid:tecnocorte-logo", html)  # Verifica que el logo está embebido
        self.assertEqual(mail.outbox[0].attachments[0].get("Content-ID"), "<tecnocorte-logo>")  # Verifica el Content-ID del logo

    # Verifica que no se puede reservar en una fecha pasada
    def test_no_permite_reservar_fecha_pasada(self):
        lunes_pasado = date.today() - timedelta(days=date.today().weekday() + 7)  # Calcula un lunes del pasado
        disponible, mensaje = cita_disponible(  # Intenta reservar en esa fecha
            lunes_pasado.isoformat(), "10:00", self.peluqueria.id, "Corte de Cabello"
        )
        self.assertFalse(disponible)  # No debe estar disponible
        self.assertIn("pasada", mensaje)  # El mensaje debe mencionar "pasada"

    # Verifica que un cliente no puede acceder al panel de admin
    def test_cliente_no_entra_a_panel_admin(self):
        self.iniciar_sesion(self.cliente)  # Inicia sesión como cliente
        response = self.client.get(reverse("sena:admin_dashboard"))  # Intenta acceder al admin
        self.assertRedirects(response, reverse("sena:login"))  # Debe ser redirigido al login

    # Verifica que el cambio de contraseña usa la cuenta de la sesión
    def test_cambio_password_usa_la_cuenta_de_la_sesion(self):
        self.iniciar_sesion(self.cliente)  # Inicia sesión
        response = self.client.get(reverse("sena:cambiar_password"))  # Abre el formulario

        self.assertContains(response, self.cliente.email)  # Debe mostrar el email del usuario
        response = self.client.post(reverse("sena:cambiar_password"), {  # Envía nueva contraseña
            "password_actual": "cliente123",
            "password": "ClienteNueva123!",
            "password_confirm": "ClienteNueva123!",
        })

        self.assertRedirects(response, reverse("sena:usuario_perfil"))  # Debe redirigir al perfil
        self.cliente.refresh_from_db()  # Recarga datos de la base
        self.assertTrue(check_password("ClienteNueva123!", self.cliente.password))  # Verifica que la contraseña se actualizó

    # Verifica que el mensaje de ayuda llega al correo oficial y crea notificación
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", CONTACT_EMAIL="tecnocorte083@gmail.com")
    def test_mensaje_de_ayuda_llega_al_correo_oficial_y_al_panel(self):
        admin = Usuario.objects.create(  # Crea un admin para recibir notificación
            nombre="Admin", apellido="Prueba", email="admin@test.com",
            password=make_password("admin123"), rol="Admin"
        )
        response = self.client.post(reverse("sena:ayuda"), {  # Envía formulario de ayuda
            "nombre": "Visitante",
            "email": "visitante@test.com",
            "asunto": "Consulta de horarios",
            "mensaje": "¿Qué horarios tienen disponibles?",
        })

        self.assertEqual(response.status_code, 200)  # Debe responder 200
        self.assertEqual(mail.outbox[0].to, ["tecnocorte083@gmail.com"])  # Correo va al email oficial
        self.assertIn("Consulta de horarios", mail.outbox[0].subject)  # El asunto contiene el asunto del mensaje
        self.assertTrue(Notificacion.objects.filter(usuario=admin, mensaje__contains="Consulta de horarios").exists())  # Se creó notificación para el admin

    # Verifica que el serializer de reserva incluye y valida el campo servicio
    def test_serializer_incluye_y_valida_servicio(self):
        serializer = ReservaSerializer(data={  # Intenta crear una reserva con servicio inválido
            "cliente": self.cliente.id,
            "peluquero": self.barbero.id,
            "peluqueria": self.peluqueria.id,
            "fecha": "2099-01-03",
            "hora": "10:00",
            "servicio": "Servicio inexistente",  # Servicio que no existe
            "estado": "Pendiente",
        })
        self.assertIn("servicio", serializer.fields)  # El campo servicio debe existir
        self.assertFalse(serializer.is_valid())  # No debe ser válido
