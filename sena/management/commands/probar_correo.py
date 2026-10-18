"""Comprueba la conexión de correo sin depender de una reserva o compra."""

from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envía un correo de prueba usando la configuración actual."

    def add_arguments(self, parser):
        parser.add_argument("destinatario", help="Correo que recibirá la prueba")

    def handle(self, *args, **options):
        destinatario = options["destinatario"]
        try:
            connection = get_connection(fail_silently=False)
            enviados = send_mail(
                "Prueba de correo de TecnoCorte",
                "La configuración de correo de TecnoCorte funciona correctamente.",
                settings.DEFAULT_FROM_EMAIL,
                [destinatario],
                fail_silently=False,
                connection=connection,
            )
        except Exception as error:
            raise CommandError(
                "No se pudo conectar con el servidor de correo. Revisa EMAIL_HOST, "
                "EMAIL_PORT, EMAIL_USE_TLS y que EMAIL_HOST_PASSWORD sea una "
                f"contraseña de aplicación válida. Detalle: {error}"
            ) from error
        self.stdout.write(self.style.SUCCESS(f"Correo enviado a {destinatario}: {enviados}"))
