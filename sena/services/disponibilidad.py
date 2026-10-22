"""Reglas reutilizables de disponibilidad de citas.

Este módulo mantiene la lógica de agenda fuera de las vistas web y de los
serializadores, sin cambiar las URLs públicas del proyecto.
"""
from datetime import datetime, timedelta

from django.utils import timezone
from django.db.models import Avg

from ..models import BloqueoHorario, HorarioTrabajo, Reserva, Usuario
from .catalogo import minutos_servicio


def cita_disponible(fecha_texto, hora_texto, peluqueria_id=None, servicio=None):
    try:
        fecha = datetime.strptime(fecha_texto, "%Y-%m-%d").date()
        hora = datetime.strptime(hora_texto, "%H:%M").time()
    except (TypeError, ValueError):
        return False, "La fecha o la hora no son válidas."
    if hora.minute % 30:
        return False, "Las citas solo pueden comenzar en intervalos de 30 minutos (00 o 30)."
    if fecha < timezone.localdate():
        return False, "No puedes reservar una fecha pasada."
    ahora = timezone.localtime()
    if fecha == ahora.date() and hora <= ahora.time().replace(second=0, microsecond=0):
        return False, "No puedes reservar una hora que ya pasó. Elige una hora posterior a la actual."
    horarios = HorarioTrabajo.objects.filter(dia_semana=fecha.weekday())
    if peluqueria_id:
        horarios = horarios.filter(peluqueria_id=peluqueria_id)
    horario = horarios.first()
    if horario is None:
        return False, "Esta barbería todavía no tiene horarios configurados."
    if not horario.activo:
        return False, "Ese día no se trabaja. Elige otra fecha."
    duracion = minutos_servicio(servicio)
    hora_fin_servicio = (datetime.combine(fecha, hora) + timedelta(minutes=duracion)).time()
    if hora < horario.hora_inicio or hora_fin_servicio > horario.hora_fin:
        return False, "La hora elegida está por fuera del horario de atención."
    bloqueos = BloqueoHorario.objects.filter(fecha=fecha)
    if peluqueria_id:
        bloqueos = bloqueos.filter(peluqueria_id=peluqueria_id)
    if bloqueos.filter(hora__isnull=True).exists():
        return False, "Ese día está bloqueado para citas."
    inicio_bloqueo = datetime.combine(fecha, hora)
    fin_bloqueo = inicio_bloqueo + timedelta(minutes=duracion)
    for bloqueo in bloqueos.exclude(hora__isnull=True):
        bloqueo_inicio = datetime.combine(fecha, bloqueo.hora)
        if inicio_bloqueo < bloqueo_inicio + timedelta(minutes=30) and fin_bloqueo > bloqueo_inicio:
            return False, "Ese horario está bloqueado. Elige otra hora."
    return True, ""


def barberos_disponibles():
    return (
        Usuario.objects.filter(rol="Barbero", activo=True, peluqueria__isnull=False)
        .select_related("peluqueria")
        .annotate(calificacion_promedio=Avg("calificaciones_recibidas__puntuacion"))
        .order_by("nombre", "apellido")
    )


def formato_cita(reserva):
    fecha = reserva.fecha if hasattr(reserva.fecha, "strftime") else datetime.strptime(str(reserva.fecha), "%Y-%m-%d").date()
    hora = reserva.hora if hasattr(reserva.hora, "strftime") else datetime.strptime(str(reserva.hora), "%H:%M").time()
    return f"{fecha.strftime('%d/%m/%Y')} a las {hora.strftime('%H:%M')}"


def barbero_esta_disponible(barbero_id, fecha_texto, hora_texto, servicio, reserva_actual=None):
    try:
        inicio = datetime.combine(datetime.strptime(fecha_texto, "%Y-%m-%d").date(), datetime.strptime(hora_texto, "%H:%M").time())
    except (TypeError, ValueError):
        return False, "La fecha o la hora no son válidas."
    fin = inicio + timedelta(minutes=minutos_servicio(servicio))
    citas = Reserva.objects.filter(peluquero_id=barbero_id, fecha=fecha_texto).exclude(estado="Cancelada")
    if reserva_actual:
        citas = citas.exclude(id=reserva_actual.id)
    for cita in citas:
        inicio_existente = datetime.combine(cita.fecha, cita.hora)
        fin_existente = inicio_existente + timedelta(minutes=minutos_servicio(cita.servicio))
        if inicio < fin_existente and fin > inicio_existente:
            return False, "El barbero ya tiene una cita que ocupa ese horario."
    return True, ""
