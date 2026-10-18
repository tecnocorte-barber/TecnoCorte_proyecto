# Pruebas de las funciones de fotos de productos, moderación de imágenes y configuración.
import tempfile
from io import BytesIO

from django.contrib.staticfiles import finders
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
            # Todas las pantallas de panel llevan el header con Dashboard y perfil.
            self.assertContains(r, "data-panel-actions", msg_prefix=url)

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
            reverse("sena:peluquero_configuracion"),
        ]
        for url in barbero_urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, "panel-glass", msg_prefix=url)
            self.assertContains(r, "data-panel-actions", msg_prefix=url)

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

    def test_la_tabla_de_usuarios_no_saca_scroll_horizontal(self):
        """Anchos en porcentaje y correo recortado: la tabla nunca desborda."""
        self.login()
        Usuario.objects.create(
            nombre="Juan", apellido="Perez",
            email="un.correo.larguisimo.de.prueba@tecnocorte.com",
            password="x", rol="Cliente",
        )
        r = self.client.get(reverse("sena:admin_usuarios"))
        h = r.content.decode()
        self.assertContains(r, 'class="w-full text-left tc-table"')  # table-layout: fixed
        self.assertEqual(h.count('<col style="width:'), 7)  # columnas en porcentaje
        self.assertIn("tc-truncate", h)  # el correo se recorta con "..."
        self.assertIn('title="un.correo.larguisimo.de.prueba@tecnocorte.com"', h)
        self.assertNotIn("overflow-x-auto", h)  # sin la barra nativa del navegador

    def test_la_tabla_de_usuarios_es_compacta(self):
        """Filas bajas (una línea y avatar pequeño) para que el cuadro no crezca."""
        self.login()
        r = self.client.get(reverse("sena:admin_usuarios"))
        h = r.content.decode()
        self.assertNotIn(">ID: USR-", h)  # el ID vive en el tooltip, no gasta renglón
        self.assertIn("· ID: USR-", h)
        self.assertIn("h-8 w-8 shrink-0 items-center", h)  # inicial compacta
        self.assertNotIn("h-10 w-10", h)  # sin el avatar alto de antes
        self.assertNotIn("mb-10", h)  # menos aire entre los bloques de arriba
        with open(finders.find("css/base/premium.css"), encoding="utf-8") as archivo:
            css = archivo.read()
        self.assertIn("padding: 8px 12px;", css)  # celdas compactas
        self.assertIn(".tc-table td[colspan]", css)  # "sin datos" respira igual

    def test_las_barras_de_desplazamiento_son_del_tema(self):
        """Nada de la barra gris nativa: el CSS define una fina y del tema."""
        with open(finders.find("css/base/premium.css"), encoding="utf-8") as archivo:
            css = archivo.read()
        self.assertIn("::-webkit-scrollbar-thumb", css)
        self.assertIn("scrollbar-width: thin", css)  # Firefox
        self.assertIn("background-clip: content-box", css)  # pulgar fino e insetado

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


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ZonaConfiguracionTests(TestCase):
    """Zona de Configuración de cliente y barbero, header unificado y reserva inteligente."""

    def setUp(self):
        from .models import Peluqueria

        self.peluqueria = Peluqueria.objects.create(
            nombre="Barberia Central", ubicacion="Calle 1", telefono="300-1111",
        )
        self.cliente = Usuario.objects.create(
            nombre="Ana", apellido="Gomez", email="ana@test.com", password="x",
            rol="Cliente", telefono="300-2222",
        )
        self.barbero = Usuario.objects.create(
            nombre="Luis", apellido="Rios", email="luis@test.com", password="x",
            rol="Barbero", peluqueria=self.peluqueria,
        )
        self.admin = Usuario.objects.create(
            nombre="Root", apellido="Admin", email="root@test.com", password="x",
            rol="Admin",
        )

    def sesion(self, usuario):
        s = self.client.session
        s["logueado"] = {"id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol}
        s.save()

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    # ---------- Configuracion del cliente ----------

    def test_cliente_entra_a_su_configuracion_y_ve_las_cuatro_pestanas(self):
        self.sesion(self.cliente)
        for pestana in ("perfil", "seguridad", "notificaciones", "privacidad"):
            r = self.client.get(reverse("sena:usuario_configuracion") + "?seccion=" + pestana)
            self.assertEqual(r.status_code, 200, pestana)
        # Una seccion desconocida cae en la primera pestana, no en un error.
        r = self.client.get(reverse("sena:usuario_configuracion") + "?seccion=xyz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["pestana"], "perfil")

    def test_configuracion_bloquea_aotros_roles(self):
        self.sesion(self.barbero)
        r = self.client.get(reverse("sena:usuario_configuracion"))
        self.assertEqual(r.status_code, 302)

    def test_actualizar_perfil_desde_configuracion(self):
        self.sesion(self.cliente)
        self.client.post(reverse("sena:usuario_configuracion") + "?seccion=perfil", {
            "accion": "perfil", "nombre": "Ana M.", "apellido": "Gomez",
            "telefono": "300-9999",
        })
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre, "Ana M.")
        self.assertEqual(self.cliente.telefono, "300-9999")
        # El header muestra el nombre nuevo sin volver a entrar.
        self.assertEqual(self.client.session["logueado"]["nombre"], "Ana M.")

    def test_notificaciones_se_guardan_en_el_usuario(self):
        self.sesion(self.cliente)
        self.client.post(reverse("sena:usuario_configuracion") + "?seccion=notificaciones", {
            "accion": "notificaciones", "correo": "on", "anticipacion": "48",
        })
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.aviso_correo)
        self.assertFalse(self.cliente.aviso_whatsapp)  # No viene en el POST
        self.assertFalse(self.cliente.aviso_sms)
        self.assertEqual(self.cliente.aviso_anticipacion_horas, 48)

    def test_anticipacion_no_numerica_usa_el_valor_por_defecto(self):
        self.sesion(self.cliente)
        self.client.post(reverse("sena:usuario_configuracion") + "?seccion=notificaciones", {
            "accion": "notificaciones", "anticipacion": "mucho",
        })
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.aviso_anticipacion_horas, 24)

    def test_descarga_de_datos_entrega_un_json(self):
        self.sesion(self.cliente)
        r = self.client.post(reverse("sena:usuario_configuracion") + "?seccion=privacidad", {"accion": "descarga"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        datos = r.json()
        self.assertEqual(datos["perfil"]["email"], "ana@test.com")
        self.assertEqual(datos["reservas"], [])

    # ---------- Configuracion del barbero ----------

    def test_barbero_entra_a_su_configuracion(self):
        self.sesion(self.barbero)
        for pestana in ("portafolio", "agenda", "servicios", "notificaciones"):
            r = self.client.get(reverse("sena:peluquero_configuracion") + "?seccion=" + pestana)
            self.assertEqual(r.status_code, 200, pestana)
        # En Agenda ve los horarios de su peluqueria.
        r = self.client.get(reverse("sena:peluquero_configuracion") + "?seccion=agenda")
        self.assertEqual(r.context["peluqueria"], self.peluqueria)

    def test_configuracion_del_barbero_bloquea_aotros_roles(self):
        self.sesion(self.cliente)
        r = self.client.get(reverse("sena:peluquero_configuracion"))
        self.assertEqual(r.status_code, 302)

    def test_barbero_actualiza_su_portafolio(self):
        self.sesion(self.barbero)
        self.client.post(reverse("sena:peluquero_configuracion") + "?seccion=portafolio", {
            "accion": "portafolio", "nombre": "Luis A.", "apellido": "Rios",
            "telefono": "300-3333",
        })
        self.barbero.refresh_from_db()
        self.assertEqual(self.barbero.nombre, "Luis A.")
        self.assertEqual(self.barbero.telefono, "300-3333")

    # ---------- Header unificado ----------

    def test_header_de_panel_ofrece_dashboard_perfil_configuracion_y_salida(self):
        self.sesion(self.admin)
        r = self.client.get(reverse("sena:admin_dashboard"))
        self.assertContains(r, "data-panel-actions")
        self.assertContains(r, reverse("sena:admin_dashboard"))
        self.assertContains(r, reverse("sena:admin_perfil"))
        self.assertContains(r, reverse("sena:admin_configuracion"))
        self.assertContains(r, reverse("sena:logout"))

    def test_sidebars_dejan_de_repetir_perfil_tema_y_salida(self):
        self.sesion(self.admin)
        r = self.client.get(reverse("sena:admin_dashboard"))
        self.assertContains(r, "Nueva cita")
        # La salida aparece una sola vez: en el dropdown del header, no en el sidebar.
        self.assertEqual(r.content.count(b"panel-header-menu-item hover:text-error"), 1)
        self.sesion(self.barbero)
        r = self.client.get(reverse("sena:peluquero_dashboard"))
        self.assertEqual(r.content.count(b"panel-header-menu-item hover:text-error"), 1)

    def test_nav_publico_usa_el_mismo_dropdown_de_perfil(self):
        self.sesion(self.cliente)
        r = self.client.get(reverse("sena:usuario_dashboard"))
        self.assertContains(r, "data-panel-actions")
        self.assertContains(r, reverse("sena:usuario_configuracion"))

    def test_las_paginas_de_cliente_centralizan_la_salida_en_el_dropdown(self):
        """Perfil, notificaciones, reserva y carrito usan el header unificado.

        Estas páginas conservan además un ``<nav class="hidden">`` heredado que
        nunca se muestra, así que lo que hay que comprobar es que la barra
        visible (site_nav) trae el desplegable y que la salida aparece una sola
        vez, dentro de ese desplegable.
        """
        paginas = [
            reverse("sena:usuario_perfil"),
            reverse("sena:usuario_notificaciones"),
            reverse("sena:usuario_reservar_cita"),
            reverse("sena:carrito"),
        ]
        for pagina in paginas:
            self.sesion(self.cliente)
            r = self.client.get(pagina)
            self.assertEqual(r.status_code, 200, pagina)
            self.assertContains(r, "data-panel-actions", msg_prefix=pagina)
            # La salida vive solo en el desplegable del header, nunca como enlace suelto.
            self.assertEqual(
                r.content.count(b"panel-header-menu-item hover:text-error"), 1, pagina
            )

    def test_perfil_de_cliente_ofrece_configuracion_y_no_salida_suelta(self):
        self.sesion(self.cliente)
        r = self.client.get(reverse("sena:usuario_perfil"))
        self.assertContains(r, reverse("sena:usuario_configuracion"))
        # El "Cerrar Sesión" que colgaba bajo el formulario se sustituyó por Configuración.
        self.assertNotContains(r, ">Cerrar Sesión<")

    # ---------- Reserva inteligente ----------

    def test_catalogo_de_servicios_preselecciona_el_servicio(self):
        self.sesion(self.cliente)
        r = self.client.get(reverse("sena:usuario_servicios"))
        self.assertContains(r, "usuario/reservar_cita/?servicio=Corte%20de%20Cabello")

    def test_reservar_cita_acepta_servicio_y_sucursal_iniciales(self):
        self.sesion(self.cliente)
        r = self.client.get(
            reverse("sena:usuario_reservar_cita")
            + "?servicio=Combo%20Completo&peluqueria=" + str(self.peluqueria.id)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["servicio_inicial"], "Combo Completo")
        self.assertEqual(r.context["peluqueria_inicial"], str(self.peluqueria.id))
        # Un servicio inventado no se preselecciona.
        r = self.client.get(reverse("sena:usuario_reservar_cita") + "?servicio=Hacked")
        self.assertEqual(r.context["servicio_inicial"], "")

    def test_barbero_no_puede_reservar_en_otra_sucursal(self):
        from .models import Peluqueria

        otra = Peluqueria.objects.create(nombre="Otra", ubicacion="Calle 2", telefono="300-3333")
        self.sesion(self.cliente)
        r = self.client.post(reverse("sena:usuario_pre_confirmar"), {
            "peluquero": self.barbero.id, "peluqueria": otra.id,
            "servicio": "Corte de Cabello", "fecha": "2030-01-10", "hora": "10:00",
        })
        self.assertContains(r, "no pertenece a la barber")
        # Si puede en su peluqueria real (el horario se rechaza despues, no la sucursal).
        r = self.client.post(reverse("sena:usuario_pre_confirmar"), {
            "peluquero": self.barbero.id, "peluqueria": self.peluqueria.id,
            "servicio": "Corte de Cabello", "fecha": "2030-01-10", "hora": "10:00",
        })
        self.assertNotContains(r, "no pertenece a la barber")

    # ---------- Contacto, mensajes y politicas ----------

    def test_ayuda_acepta_tipo(self):
        from .models import MensajeContacto

        r = self.client.post(reverse("sena:ayuda"), {
            "nombre": "Carla", "email": "carla@test.com", "tipo": "cita", "mensaje": "Hola",
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MensajeContacto.objects.get().tipo, "cita")

    def test_ayuda_respeta_el_asunto_libre_antiguo(self):
        from .models import MensajeContacto

        r = self.client.post(reverse("sena:ayuda"), {
            "nombre": "Pedro", "email": "pedro@test.com", "asunto": "Asunto libre", "mensaje": "Hola",
        })
        self.assertEqual(r.status_code, 200)
        mensaje = MensajeContacto.objects.get()
        self.assertEqual(mensaje.asunto, "Asunto libre")
        self.assertEqual(mensaje.tipo, "otro")

    def test_admin_redirige_al_dashboard(self):
        self.sesion(self.admin)
        r = self.client.get(reverse("sena:inicio"))
        self.assertRedirects(r, reverse("sena:admin_dashboard"))
        r = self.client.get(reverse("sena:login"))
        self.assertRedirects(r, reverse("sena:admin_dashboard"))

    def test_admin_mensajes_muestra_tipo_y_abre_modal(self):
        from .models import MensajeContacto

        MensajeContacto.objects.create(
            nombre="Carla", email="carla@test.com", asunto="Cita", tipo="cita", mensaje="Detalle",
        )
        self.sesion(self.admin)
        r = self.client.get(reverse("sena:admin_mensajes"))
        self.assertContains(r, "Carla")
        self.assertContains(r, "carla@test.com")
        self.assertContains(r, "Cita")
        self.assertContains(r, "data-mensaje")

    def test_galeria_del_admin_filtra_por_peluqueria(self):
        self.sesion(self.admin)
        # Con una foto publicada, el filtro "Todas" y el de la barbería aparecen.
        buffer = BytesIO()
        Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
        archivo = SimpleUploadedFile("g.png", buffer.getvalue(), content_type="image/png")
        ImagenPeluqueria.objects.create(peluqueria=self.peluqueria, imagen=archivo, descripcion="x")
        r = self.client.get(reverse("sena:admin_galeria"))
        self.assertContains(r, "galeria-filtro")
        self.assertContains(r, "Todas")
        self.assertContains(r, "galeria-item")
        self.assertContains(r, 'data-peluqueria="' + str(self.peluqueria.id) + '"')

    def test_pagina_de_politicas_y_enlace_en_el_pie(self):
        self.assertEqual(self.client.get(reverse("sena:politicas")).status_code, 200)
        r = self.client.get(reverse("sena:ayuda"))
        self.assertContains(r, reverse("sena:politicas"))
