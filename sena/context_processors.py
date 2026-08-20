def carrito_contexto(request):
    """Expone el total de unidades del carrito en cualquier plantilla."""
    cantidad = 0
    carrito = request.session.get("carrito", {})
    for valor in carrito.values():
        try:
            cantidad += max(int(valor), 0)
        except (TypeError, ValueError):
            continue
    return {"cantidad": cantidad}
