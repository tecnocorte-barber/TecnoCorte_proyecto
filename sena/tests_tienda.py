# Pruebas de la tienda: el botón de favoritos se guarda en el navegador y los
# productos favoritos quedan siempre arriba en la grilla.
import pathlib

from django.test import TestCase
from django.urls import reverse

from .models import Producto


class FavoritosDeLaTiendaTests(TestCase):
    """Los favoritos de la tienda se marcan en cada tarjeta y van primero."""

    def setUp(self):
        self.pomada = Producto.objects.create(
            nombre="Pomada para el Cabello", precio=45900, stock=10,
        )
        self.aceite = Producto.objects.create(
            nombre="Aceite para Barba", precio=35900, stock=10,
        )

    def plantilla(self):
        return (
            pathlib.Path(__file__).resolve().parent
            / "templates" / "usuarios" / "usuario_tienda.html"
        ).read_text(encoding="utf-8")

    def test_cada_producto_tiene_su_boton_de_favorito(self):
        r = self.client.get(reverse("sena:usuario_tienda"))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        # Un botón por tarjeta (el script también nombra la clase, por eso se
        # busca el atributo completo).
        self.assertEqual(html.count('class="producto-favorito'), 2)
        self.assertIn(f'data-producto-id="{self.pomada.id}"', html)
        self.assertIn(f'data-producto-id="{self.aceite.id}"', html)

    def test_los_favoritos_se_guardan_en_el_navegador(self):
        html = self.plantilla()
        self.assertIn("tc-favoritos", html)  # Nombre de la clave guardada
        self.assertIn("localStorage.setItem", html)  # Se recuerdan al recargar
        self.assertIn("favorite_border", html)  # Estado sin marcar
        self.assertIn('"favorite"', html)  # Estado marcado

    def test_el_corazon_se_rellena_al_marcarlo(self):
        """El corazón relleno distingue el favorito (eje FILL de la fuente)."""
        html = self.plantilla()
        self.assertIn("fontVariationSettings", html)
        self.assertIn('"FILL" 1', html)
        self.assertIn('activo ? "favorite" : "favorite_border"', html)

    def test_marcar_un_favorito_avisa_con_un_toast(self):
        """Igual que al añadir al carrito: avisa al guardarlo y al quitarlo."""
        html = self.plantilla()
        self.assertIn("se guardó en favoritos", html)
        self.assertIn("se quitó de favoritos", html)
        self.assertIn("TecnoCorteNotify.success", html)
        self.assertIn("TecnoCorteNotify.info", html)

    def test_el_boton_de_favorito_lleva_el_nombre_del_producto(self):
        r = self.client.get(reverse("sena:usuario_tienda"))
        self.assertContains(r, 'data-nombre="Pomada para el Cabello"')
        self.assertContains(r, 'data-nombre="Aceite para Barba"')

    def test_agregar_al_carrito_usa_el_aviso_compartido(self):
        """Tienda y detalle comparten el parcial que añade sin recargar."""
        raiz = pathlib.Path(__file__).resolve().parent / "templates"
        for nombre in (
            "usuarios/usuario_tienda.html",
            "usuarios/usuario_producto_detalle.html",
        ):
            with self.subTest(plantilla=nombre):
                contenido = (raiz / nombre).read_text(encoding="utf-8")
                self.assertIn(
                    'include "includes/agregar_carrito_ajax.html"', contenido
                )

        detalle = self.client.get(
            reverse("sena:usuario_producto_detalle", args=[self.pomada.id])
        )
        self.assertEqual(detalle.status_code, 200)
        html = detalle.content.decode()
        self.assertIn("add-to-cart-form", html)  # El detalle ya no recarga
        self.assertIn('"X-Requested-With": "XMLHttpRequest"', html)

    def test_agregar_al_carrito_por_ajax_responde_con_mensaje(self):
        r = self.client.post(
            reverse("sena:agregar_carrito", args=[self.pomada.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200)
        datos = r.json()
        self.assertIn("se agregó al carrito", datos["mensaje"])
        self.assertEqual(datos["cantidad"], 1)

    def test_los_favoritos_quedan_arriba_en_la_grilla(self):
        html = self.plantilla()
        # El reordenamiento deja los favoritos primero y luego respeta el criterio.
        self.assertIn("TecnoCorteOrdenarProductos", html)
        self.assertIn("favoritos.indexOf", html)
        self.assertIn("appendChild", html)
        # El botón reordena al marcar y desmarcar.
        self.assertIn("pintar();", html)
        self.assertIn("ordenar();", html)

    def test_el_ordenar_por_reutiliza_el_mismo_reordenamiento(self):
        html = self.plantilla()
        # El selector delega en la misma función, para no perder los favoritos.
        self.assertIn("window.TecnoCorteOrdenarProductos = ordenar", html)
        self.assertEqual(html.count("grid.appendChild"), 1)
