# Pruebas de las funciones de fotos de productos, moderación de imágenes y configuración.
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse, NoReverseMatch
from PIL import Image

from .models import Configuracion, ImagenPeluqueria, Peluqueria, Producto, Usuario


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class FotosYConfiguracionTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create(
            nombre="Admin", apellido="Uno", email="admin@test.com",
            password="x", rol="Admin", activo=True,
        )
        self.peluqueria = Peluqueria.objects.create(nombre="Barber", ubicacion="Calle Falsa 123", telefono="300-0000")

    def login(self):
        s = self.client.session
        s["logueado"] = {"id": self.admin.id, "nombre": "Admin", "rol": "Admin"}
        s.save()

    def tearDown(self):
        # La configuración se cachea; se limpia para no filtrar valores entre pruebas.
        from django.core.cache import cache

        cache.clear()

    def img(self, nombre="f.png"):
        buffer = BytesIO()
        Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
        return SimpleUploadedFile(nombre, buffer.getvalue(), content_type="image/png")

    def test_crear_producto_con_imagen_y_quitarla(self):
        self.login()
        r = self.client.post(reverse("sena:admin_crear_producto"), {
            "nombre": "Cera", "descripcion": "d", "precio": "1000", "stock": "5",
            "categoria": "Cuidado", "disponible": "on", "imagen": self.img(),
        })
        self.assertEqual(r.status_code, 302)
        p = Producto.objects.get(nombre="Cera")
        self.assertTrue(p.imagen)
        self.assertIn("/media/productos/", p.imagen.url)

        # La lista del admin muestra la miniatura.
        r = self.client.get(reverse("sena:admin_productos"))
        self.assertContains(r, "productos/")

        # Quitar la foto.
        r = self.client.post(reverse("sena:admin_quitar_imagen_producto", args=[p.id]), {"motivo": "No corresponde al producto"})
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertFalse(p.imagen)

    def test_producto_rechaza_imagen_invalida_y_stock_negativo(self):
        self.login()
        archivo_invalido = SimpleUploadedFile("falso.png", b"no es una imagen", content_type="image/png")
        respuesta = self.client.post(reverse("sena:admin_crear_producto"), {
            "nombre": "Producto inválido", "descripcion": "d", "precio": "1000", "stock": "5",
            "categoria": "Cuidado", "disponible": "on", "imagen": archivo_invalido,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "imagen válida")
        self.assertFalse(Producto.objects.filter(nombre="Producto inválido").exists())

        respuesta = self.client.post(reverse("sena:admin_crear_producto"), {
            "nombre": "Stock inválido", "descripcion": "d", "precio": "1000", "stock": "-1",
            "categoria": "Cuidado", "disponible": "on",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no pueden ser negativos")
        self.assertFalse(Producto.objects.filter(nombre="Stock inválido").exists())

    def test_editar_producto_permite_quitar_imagen(self):
        self.login()
        p = Producto.objects.create(nombre="Gel", precio=1, stock=1, imagen=self.img())
        self.client.post(reverse("sena:admin_editar_producto", args=[p.id]), {
            "nombre": "Gel", "precio": "1", "stock": "1", "categoria": "Cuidado",
            "quitar_imagen": "on",
        })
        p.refresh_from_db()
        self.assertFalse(p.imagen)

    def test_quitar_foto_peluqueria_y_galeria(self):
        self.login()
        self.peluqueria.imagen = self.img()
        self.peluqueria.save()
        foto = ImagenPeluqueria.objects.create(peluqueria=self.peluqueria, imagen=self.img())

        self.client.post(reverse("sena:admin_quitar_foto_peluqueria", args=[self.peluqueria.id]), {"motivo": "Foto inapropiada"})
        self.peluqueria.refresh_from_db()
        self.assertFalse(self.peluqueria.imagen)

        r = self.client.get(reverse("sena:admin_galeria"))
        self.assertEqual(r.status_code, 200)
        self.client.post(reverse("sena:admin_eliminar_imagen_galeria", args=[foto.id]), {"motivo": "No cumple las normas"})
        self.assertFalse(ImagenPeluqueria.objects.filter(id=foto.id).exists())

    def test_paginas_renderizan_sin_errores(self):
        self.login()
        p = Producto.objects.create(nombre="X", precio=1, stock=1)
        urls = [
            reverse("sena:admin_productos"),
            reverse("sena:admin_crear_producto"),
            reverse("sena:admin_editar_producto", args=[p.id]),
            reverse("sena:admin_peluquerias"),
            reverse("sena:admin_galeria"),
            reverse("sena:admin_configuracion"),
            reverse("sena:admin_usuarios"),
            reverse("sena:usuario_tienda"),
            reverse("sena:usuario_peluquerias"),
            reverse("sena:usuario_peluqueria_detalle", args=[self.peluqueria.id]),
            reverse("sena:registro"),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_paginas_de_panel_glass_renderizan(self):
        """Todas las páginas con los menús de cristal (Admin y Barbero) responden."""
        self.login()
        barbero = Usuario.objects.create(
            nombre="B", apellido="A", email="bar@test.com", password="x",
            rol="Barbero", peluqueria=self.peluqueria,
        )
        admin_urls = [
            reverse("sena:admin_dashboard"),
            reverse("sena:admin_reservas"),
            reverse("sena:admin_peluqueros"),
            reverse("sena:admin_crear_peluquero"),
            reverse("sena:admin_editar_peluquero", args=[barbero.id]),
            reverse("sena:admin_usuarios"),
            reverse("sena:admin_crear_usuario"),
            reverse("sena:admin_editar_usuario", args=[barbero.id]),
            reverse("sena:admin_peluquerias"),
            reverse("sena:admin_crear_peluqueria"),
            reverse("sena:admin_editar_peluqueria", args=[self.peluqueria.id]),
            reverse("sena:admin_productos"),
            reverse("sena:admin_crear_producto"),
            reverse("sena:admin_mensajes"),
            reverse("sena:admin_notificaciones"),
            reverse("sena:admin_ingresos"),
            reverse("sena:admin_horarios"),
            reverse("sena:admin_galeria"),
            reverse("sena:admin_configuracion"),
            reverse("sena:admin_perfil"),
            reverse("sena:admin_crear_reserva"),
        ]
        for url in admin_urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, "panel-glass", msg_prefix=url)

        # Ahora como barbero: ve sus páginas con el menú de cristal.
        s = self.client.session
        s["logueado"] = {"id": barbero.id, "nombre": "B", "rol": "Barbero"}
        s.save()
        barbero_urls = [
            reverse("sena:peluquero_dashboard"),
            reverse("sena:peluquero_editar_peluqueria"),
            reverse("sena:peluquero_galeria"),
            reverse("sena:peluquero_perfil"),
            reverse("sena:peluquero_notificaciones"),
            reverse("sena:peluquero_crear_cita"),
        ]
        for url in barbero_urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, "panel-glass", msg_prefix=url)

        # Como cliente, el menú normal (site_nav) no usa el cristal.
        cliente = Usuario.objects.create(
            nombre="C", apellido="L", email="cli@test.com", password="x", rol="Cliente",
        )
        s = self.client.session
        s["logueado"] = {"id": cliente.id, "nombre": "C", "rol": "Cliente"}
        s.save()
        r = self.client.get(reverse("sena:usuario_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "panel-glass")

    def test_quitar_foto_usuario(self):
        self.login()
        u = Usuario.objects.create(nombre="Juan", apellido="P", email="j@test.com", password="x", rol="Cliente", foto=self.img())
        self.assertEqual(self.client.get(reverse("sena:admin_usuarios")).status_code, 200)
        self.client.post(reverse("sena:admin_quitar_foto_usuario", args=[u.id]), {"motivo": "No es una persona"})
        u.refresh_from_db()
        self.assertFalse(u.foto)

    def test_borrar_foto_sin_motivo_no_elimina_y_avisa(self):
        """Sin motivo escrito no se borra ninguna foto."""
        self.login()
        self.peluqueria.imagen = self.img()
        self.peluqueria.save()
        r = self.client.post(
            reverse("sena:admin_quitar_foto_peluqueria", args=[self.peluqueria.id]),
            {"motivo": "   "},
            follow=True,
        )
        self.peluqueria.refresh_from_db()
        self.assertTrue(self.peluqueria.imagen)
        self.assertContains(r, "Debes escribir el motivo")

    def test_motivo_se_envia_por_correo_al_autor(self):
        """El motivo del borrado llega por correo a quien subió la foto."""
        from django.core import mail

        self.login()
        dueno = Usuario.objects.create(
            nombre="Dueño", apellido="Barber", email="dueno@test.com",
            password="x", rol="Barbero", foto=self.img(),
        )
        self.peluqueria.dueno = dueno
        self.peluqueria.imagen = self.img()
        self.peluqueria.save()

        self.client.post(
            reverse("sena:admin_quitar_foto_peluqueria", args=[self.peluqueria.id]),
            {"motivo": "La foto no es de la barbería"},
        )
        self.assertTrue(any("dueno@test.com" in m.to for m in mail.outbox))
        self.assertTrue(any("La foto no es de la barbería" in m.body for m in mail.outbox))

    def test_crear_barbero_sin_peluqueria_es_rechazado(self):
        """Al crear un barbero la barbería es obligatoria."""
        self.login()
        r = self.client.post(reverse("sena:admin_crear_usuario"), {
            "nombre": "B", "apellido": "A", "email": "b@test.com",
            "password": "Abcdef1!", "telefono": "", "rol": "Barbero",
        })
        self.assertEqual(r.status_code, 200)  # Vuelve al formulario con el error
        self.assertContains(r, "barbería")
        self.assertFalse(Usuario.objects.filter(email="b@test.com").exists())

    def test_barbero_asignado_por_admin_no_crea_su_peluqueria(self):
        """El barbero ya no puede crear su propia peluquería; la asigna el Admin."""
        with self.assertRaises(NoReverseMatch):
            reverse("sena:peluquero_crear_peluqueria")
        # Si el Admin le asigna una, el panel del barbero la reconoce.
        barbero = Usuario.objects.create(
            nombre="B", apellido="A", email="b@test.com", password="x",
            rol="Barbero", peluqueria=self.peluqueria,
        )
        s = self.client.session
        s["logueado"] = {"id": barbero.id, "nombre": "B", "rol": "Barbero"}
        s.save()
        r = self.client.get(reverse("sena:peluquero_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Aún no tienes una peluquería asignada")

    def test_configuracion_se_guarda_y_aplica(self):
        self.login()
        r = self.client.get(reverse("sena:admin_configuracion"))
        self.assertEqual(r.status_code, 200)
        self.client.post(reverse("sena:admin_configuracion"), {
            "sitio_nombre": "Mi Corte", "correo_contacto": "a@b.com",
            "texto_aviso": "hola", "mensaje_mantenimiento": "vuelvo",
            # privacidad desactivada
        })
        config = Configuracion.cargar()
        self.assertEqual(config.sitio_nombre, "Mi Corte")
        self.assertFalse(config.registro_abierto)
        self.assertFalse(config.mostrar_telefonos)

        # El registro queda cerrado.
        self.client.session.flush()
        r = self.client.get(reverse("sena:registro"))
        self.assertContains(r, "desactivado")

        # Los teléfonos/ubicaciones no se muestran en el detalle.
        r = self.client.get(reverse("sena:usuario_peluqueria_detalle", args=[self.peluqueria.id]))
        self.assertNotContains(r, "300-0000")
        self.assertNotContains(r, "Calle Falsa 123")

    def test_modo_mantenimiento_bloquea_visitantes_pero_no_admin(self):
        self.login()
        self.client.post(reverse("sena:admin_configuracion"), {
            "sitio_nombre": "TecnoCorte", "correo_contacto": "a@b.com",
            "mensaje_mantenimiento": "en obras", "modo_mantenimiento": "on",
        })
        self.assertTrue(Configuracion.cargar().modo_mantenimiento)
        # El admin sigue navegando (su dashboard responde).
        self.assertEqual(self.client.get(reverse("sena:admin_dashboard")).status_code, 200)
        # Un visitante recibe el aviso.
        self.client.session.flush()
        r = self.client.get(reverse("sena:inicio"))
        self.assertEqual(r.status_code, 503)
        self.assertContains(r, "mantenimiento", status_code=503)
