# Procesador de contexto: agrega datos del carrito de compras a todas las plantillas

# Devuelve la cantidad total de unidades del carrito guardado en la sesión
def carrito_contexto(request):
    """Expone el total de unidades del carrito en cualquier plantilla."""
    cantidad = 0
    carrito = request.session.get("carrito", {})
    # Suma las unidades de cada producto, ignorando valores inválidos o negativos
    for valor in carrito.values():
        try:
            cantidad += max(int(valor), 0)
        except (TypeError, ValueError):
            continue
    return {"cantidad": cantidad}
