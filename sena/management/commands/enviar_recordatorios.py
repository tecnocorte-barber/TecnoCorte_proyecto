"""Envía recordatorios de citas próximos y evita duplicados.

Este comando está pensado para ejecutarse cada 5 o 10 minutos con el
Programador de tareas de Windows, cron o el scheduler del proveedor donde se
publique TecnoCorte. No se ejecuta dentro de una petición web: así el correo no
ralentiza la navegación y funciona aunque no haya usuarios conectados.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from sena.models import Notificacion, Reserva
from sena.services.correos import enviar_correo


class Command(BaseCommand):
    help = "Envía recordatorios por correo para citas próximas."

    def handle(self, *args, **options):
        ahora = timezone.localtime()
        enviados = 0
        revisadas = 0
        base_url = getattr(settings, "SITE_URL", "").rstrip("/")

        reservas = (
            Reserva.objects.select_related("cliente", "peluquero", "peluqueria")
            .filter(
                cliente__activo=True,
                cliente__aviso_correo=True,
                cliente__email__isnull=False,
                recordatorio_correo_enviado__isnull=True,
                fecha__gte=ahora.date(),
            )
            .exclude(estado__in=["Cancelada", "Completada"])
            .order_by("fecha", "hora")
        )

        for reserva in reservas:
            revisadas += 1
            momento = timezone.make_aware(
                datetime.combine(reserva.fecha, reserva.hora),
                timezone.get_current_timezone(),
            )
            anticipacion = max(1, reserva.cliente.aviso_anticipacion_horas or 24)
            limite = ahora + timedelta(hours=anticipacion)

            # No avisa citas que ya pasaron ni las que todavía están fuera de
            # la ventana configurada por el cliente.
            if momento < ahora or momento > limite:
                continue

            texto = (
                f"Hola {reserva.cliente.nombre},\n\n"
                f"Te recordamos que tienes una cita de {reserva.servicio} "
                f"el {reserva.fecha.strftime('%d/%m/%Y')} a las "
                f"{reserva.hora.strftime('%H:%M')} en {reserva.peluqueria.nombre}.\n\n"
                "Si necesitas cambiarla, hazlo con anticipación desde tu perfil."
            )
            enlace = f"{base_url}{reverse('sena:usuario_editar_reserva', args=[reserva.id])}" if base_url else None
            enviado = enviar_correo(
                reserva.cliente,
                "Recordatorio de tu cita en TecnoCorte",
                texto,
                enlace=enlace,
                texto_enlace="Revisar mi cita",
            )
            if not enviado:
                self.stderr.write(
                    f"No se pudo enviar el recordatorio de la reserva #{reserva.id}; se reintentará."
                )
                continue
            Notificacion.objects.create(
                usuario=reserva.cliente,
                reserva=reserva,
                mensaje=f"Recordatorio: tienes cita de {reserva.servicio} el {reserva.fecha.strftime('%d/%m/%Y')} a las {reserva.hora.strftime('%H:%M')}.",
            )
            reserva.recordatorio_correo_enviado = ahora
            reserva.save(update_fields=["recordatorio_correo_enviado"])
            enviados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Recordatorios enviados: {enviados}. Citas revisadas: {revisadas}."
            )
        )
