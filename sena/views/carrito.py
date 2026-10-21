"""Implementaci?n del carrito y pedidos."""
from .core import *

def carrito(request):
    contexto = contexto_carrito(request)
    return render(request, "carrito/carrito.html", contexto)


def _cliente_o_invitado(request):
    """True si la sesión no está logueada o pertenece a un Cliente (los demás roles solo pueden ver la tienda/carrito)."""
    logueado = request.session.get("logueado")
    return not logueado or logueado.get("rol") == "Cliente"


def agregar_carrito(request, producto_id):
    es_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not _cliente_o_invitado(request):
        if es_ajax:
            return JsonResponse({"error": "Solo los clientes pueden agregar productos al carrito."}, status=403)
        request.session["mensaje_carrito"] = "Solo los clientes pueden agregar productos al carrito."
        return redirect("sena:carrito")
    if not carrito_visible(request):
        if request.session.get("logueado"):
            cargar_carrito_usuario(request, request.session["logueado"]["id"])
        else:
            request.session["carrito"] = {}
            request.session.pop("carrito_usuario_id", None)
    try:
        producto = Producto.objects.get(id=producto_id)
    except Producto.DoesNotExist:
        if es_ajax:
            return JsonResponse({"error": "El producto no está disponible."}, status=404)
        request.session["mensaje_tienda"] = "El producto no está disponible."
        return redirect("sena:usuario_tienda")
    if not producto.disponible or producto.stock <= 0:
        mensaje = f"No hay stock disponible de {producto.nombre}."
        if es_ajax:
            return JsonResponse({"error": mensaje}, status=409)
        request.session["mensaje_tienda"] = mensaje
        return redirect("sena:usuario_tienda")
    carrito = request.session.get("carrito", {})
    cantidad_actual = int(carrito.get(str(producto.id), 0))
    if cantidad_actual >= producto.stock:
        mensaje = f"No hay más unidades disponibles de {producto.nombre}."
        if es_ajax:
            return JsonResponse({"error": mensaje}, status=409)
        request.session["mensaje_tienda"] = mensaje
        return redirect("sena:usuario_tienda")
    carrito[str(producto.id)] = cantidad_actual + 1
    request.session["carrito"] = carrito
    if request.session.get("logueado"):
        request.session["carrito_usuario_id"] = request.session["logueado"]["id"]
    guardar_carrito_activo(request)
    if es_ajax:
        return JsonResponse({
            "cantidad": sum(int(c) for c in carrito.values()),
            "producto_id": producto.id,
            "mensaje": f"{producto.nombre} se agregó al carrito.",
        })
    messages.success(request, f"{producto.nombre} se agregó al carrito.")
    return redirect("sena:usuario_tienda")


def actualizar_carrito(request, producto_id):
    es_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not _cliente_o_invitado(request):
        if es_ajax:
            return JsonResponse({"error": "Solo los clientes pueden modificar el carrito."}, status=403)
        return redirect("sena:carrito")
    if not carrito_visible(request):
        if es_ajax:
            return JsonResponse({"error": "Este carrito no pertenece a la sesión actual."}, status=403)
        return redirect("sena:carrito")
    if request.method == "POST":
        try:
            cantidad = int(request.POST.get("cantidad", 1))
        except (TypeError, ValueError):
            cantidad = 1
        carrito = request.session.get("carrito", {})
        if str(producto_id) in carrito:
            producto = Producto.objects.filter(id=producto_id).first()
            stock = producto.stock if producto and producto.disponible else 0
            if cantidad > stock:
                cantidad = stock
                if producto:
                    request.session["mensaje_carrito"] = f"No hay suficiente stock de {producto.nombre}. Disponible: {stock}."
            if cantidad <= 0:
                del carrito[str(producto_id)]
            else:
                carrito[str(producto_id)] = cantidad
        request.session["carrito"] = carrito
        guardar_carrito_activo(request)
        if es_ajax:
            contexto = contexto_carrito(request)
            item = next((item for item in contexto["items"] if item["producto"].id == producto_id), None)
            return JsonResponse({
                "item_id": producto_id,
                "item_cantidad": item["cantidad"] if item else 0,
                "subtotal": item["subtotal"] if item else 0,
                "cantidad": contexto["cantidad"],
                "total": contexto["total"],
                "empty": not contexto["items"],
                "mensaje": contexto["mensaje_carrito"],
            })
        messages.success(request, "Carrito actualizado.")
    return redirect("sena:carrito")


def eliminar_carrito(request, producto_id):
    es_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not _cliente_o_invitado(request):
        if es_ajax:
            return JsonResponse({"error": "Solo los clientes pueden modificar el carrito."}, status=403)
        return redirect("sena:carrito")
    if not carrito_visible(request):
        if es_ajax:
            return JsonResponse({"error": "Este carrito no pertenece a la sesión actual."}, status=403)
        return redirect("sena:carrito")
    carrito = request.session.get("carrito", {})
    carrito.pop(str(producto_id), None)
    request.session["carrito"] = carrito
    guardar_carrito_activo(request)
    if es_ajax:
        contexto = contexto_carrito(request)
        return JsonResponse({
            "item_id": producto_id,
            "cantidad": contexto["cantidad"],
            "total": contexto["total"],
            "empty": not contexto["items"],
        })
    messages.info(request, "Producto eliminado del carrito.")
    return redirect("sena:carrito")


@autorizacion(["Cliente"])
def finalizar_pedido(request):
    contexto = contexto_carrito(request)
    if not contexto["items"]:
        return redirect("sena:carrito")

    if request.method == "POST":
        cliente_id = request.session["logueado"]["id"]
        with transaction.atomic():
            producto_ids = [item["producto"].id for item in contexto["items"]]
            productos = {
                producto.id: producto
                for producto in Producto.objects.select_for_update().filter(id__in=producto_ids)
            }
            error_stock = ""
            for item in contexto["items"]:
                producto = productos.get(item["producto"].id)
                if producto is None or not producto.disponible or producto.stock < item["cantidad"]:
                    disponible = producto.stock if producto and producto.disponible else 0
                    nombre = producto.nombre if producto else item["producto"].nombre
                    error_stock = f"No hay stock suficiente de {nombre}. Disponible: {disponible}."
                    break
                item["producto"] = producto
                item["subtotal"] = producto.precio * item["cantidad"]

            if error_stock:
                contexto["error"] = error_stock
                return render(request, "carrito/finalizar_pedido.html", contexto)

            contexto["total"] = sum(item["subtotal"] for item in contexto["items"])
            pedido = Pedido.objects.create(
                cliente_id=cliente_id,
                total=contexto["total"],
                estado="Pendiente"
            )
            for item in contexto["items"]:
                producto = item["producto"]
                stock_anterior = producto.stock
                PedidoProducto.objects.create(
                    pedido=pedido,
                    producto=producto,
                    cantidad=item["cantidad"],
                    precio=producto.precio
                )
                producto.stock -= item["cantidad"]
                if producto.stock == 0:
                    producto.disponible = False
                    if stock_anterior > 0:
                        notificar_producto_agotado(producto)
                producto.save(update_fields=["stock", "disponible"])
        request.session["carrito"] = {}
        productos_resumen = ", ".join(f"{item['cantidad']} x {item['producto'].nombre}" for item in contexto["items"][:3])
        if len(contexto["items"]) > 3:
            productos_resumen += f" y {len(contexto['items']) - 3} productos más"
        Notificacion.objects.create(
            usuario_id=cliente_id,
            mensaje=f"Tu pedido #{pedido.id} fue recibido: {productos_resumen}. Total: ${pedido.total:,} COP.",
        )
        cliente = Usuario.objects.get(id=cliente_id)
        enviar_correo(
            cliente,
            f"Recibimos tu pedido #{pedido.id}",
            (
                f"Hola {cliente.nombre},\n\nRecibimos tu pedido #{pedido.id} por "
                f"${pedido.total:,} COP. Puedes pagarlo y recogerlo en la tienda. "
                "Te avisaremos cuando esté listo."
            ),
            request=request,
            enlace=request.build_absolute_uri(reverse("sena:usuario_perfil")),
            texto_enlace="Ver mis pedidos",
        )
        messages.success(request, f"Pedido #{pedido.id} recibido por ${pedido.total:,} COP. Pagarás al recogerlo en la tienda.")
        return redirect("sena:pedido_exitoso", pedido_id=pedido.id)

    return render(request, "carrito/finalizar_pedido.html", contexto)


@autorizacion(["Cliente"])
def pedido_exitoso(request, pedido_id):
    pedido = Pedido.objects.filter(id=pedido_id, cliente_id=request.session["logueado"]["id"]).first()
    if pedido is None:
        return redirect("sena:usuario_perfil")
    return render(request, "carrito/pedido_exitoso.html", {"pedido": pedido})

