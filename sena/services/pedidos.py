"""Reglas de actualización y cierre de pedidos de la tienda."""

from django.db import transaction
from django.utils import timezone

from ..models import Pedido
from ..utilidades import TRANSICIONES_PEDIDO, transicion_valida


def actualizar_pedido(pedido_id, estado_solicitado, pago_confirmado):
    """Actualiza un pedido con bloqueo y lo cierra al entregarlo y cobrarlo."""
    with transaction.atomic():
        pedido = (
            Pedido.objects.select_for_update()
            .select_related("cliente")
            .filter(id=pedido_id)
            .first()
        )
        if pedido is None:
            return None, "El pedido no existe."
        if pedido.estado == "Completado":
            return pedido, "El pedido está completado y ya no admite cambios."
        estado_solicitado = estado_solicitado or pedido.estado
        estados_editables = {
            valor for valor, _etiqueta in Pedido.ESTADOS if valor != "Completado"
        }
        if estado_solicitado not in estados_editables:
            return pedido, "El estado seleccionado no es válido."
        if not transicion_valida(
            TRANSICIONES_PEDIDO, pedido.estado, estado_solicitado
        ):
            return pedido, (
                f"No se puede pasar un pedido de "
                f"{pedido.get_estado_display()} a ese estado."
            )

        ahora = timezone.now()
        pedido.pago_confirmado = pago_confirmado
        pedido.estado = (
            "Completado"
            if estado_solicitado == "Entregado" and pago_confirmado
            else estado_solicitado
        )
        pedido.fecha_pago = (
            pedido.fecha_pago or ahora if pago_confirmado else None
        )
        pedido.fecha_entrega = (
            pedido.fecha_entrega or ahora
            if estado_solicitado in {"Entregado", "Completado"}
            else None
        )
        pedido.save(
            update_fields=["estado", "pago_confirmado", "fecha_pago", "fecha_entrega"]
        )

    return pedido, None
