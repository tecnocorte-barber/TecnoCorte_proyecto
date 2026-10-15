# Pruebas de las funciones de fotos de productos, moderación de imágenes y configuración.
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

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

    def img(self, nombre="f.png"):
        return SimpleUploadedFile(nombre, b"contenido-imagen", content_type="image/png")

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
        r = self.client.post(reverse("sena:admin_quitar_imagen_producto", args=[p.id]))
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertFalse(p.imagen)

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

        self.client.post(reverse("sena:admin_quitar_foto_peluqueria", args=[self.peluqueria.id]))
        self.peluqueria.refresh_from_db()
        self.assertFalse(self.peluqueria.imagen)

        r = self.client.get(reverse("sena:admin_galeria"))
        self.assertEqual(r.status_code, 200)
        self.client.post(reverse("sena:admin_eliminar_imagen_galeria", args=[foto.id]))
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

    def test_quitar_foto_usuario(self):
        self.login()
        u = Usuario.objects.create(nombre="Juan", apellido="P", email="j@test.com", password="x", rol="Cliente", foto=self.img())
        self.assertEqual(self.client.get(reverse("sena:admin_usuarios")).status_code, 200)
        self.client.post(reverse("sena:admin_quitar_foto_usuario", args=[u.id]))
        u.refresh_from_db()
        self.assertFalse(u.foto)

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
