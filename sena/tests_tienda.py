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
            nombre="Pomada para el Cabello", precio=45900,
        )
        self.aceite = Producto.objects.create(
            nombre="Aceite para Barba", precio=35900,
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
