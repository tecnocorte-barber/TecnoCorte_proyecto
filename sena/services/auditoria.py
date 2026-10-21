"""Servicio centralizado para registrar acciones sensibles."""
import logging


logger = logging.getLogger(__name__)


def registrar_accion(request, accion, entidad="", entidad_id=None, detalle=""):
    """Guarda una acción sin permitir que la auditoría rompa la operación."""
    try:
        from sena.models import RegistroAccion, Usuario

        actor = getattr(getattr(request, "user", None), "usuario", None) if request else None
        if actor is None:
            sesion = request.session.get("logueado", {}) if request else {}
            actor = Usuario.objects.filter(id=sesion.get("id"), activo=True).first()
        RegistroAccion.objects.create(
            actor=actor,
            accion=str(accion)[:80],
            entidad=str(entidad)[:80],
            entidad_id=entidad_id,
            detalle=str(detalle or "")[:500],
            ip=(request.META.get("REMOTE_ADDR", "") if request else "")[:45],
            navegador=(request.META.get("HTTP_USER_AGENT", "") if request else "")[:200],
        )
    except Exception:
        # La auditoría es complementaria; nunca debe romper la operación,
        # pero el fallo sí debe quedar visible para poder investigarlo.
        logger.exception("No se pudo registrar la acción de auditoría: %s", accion)
