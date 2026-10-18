# Pruebas del inicio editable (el Admin elige los servicios y productos que se
# destacan) y de la sección de reseñas reales de la página principal.
from datetime import date, time

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Calificacion, Configuracion, Peluqueria, Producto, Reserva, Usuario
from .views import RESENAS_VISIBLES


class InicioEditableTests(TestCase):
    def setUp(self):
        cache.clear()
        self.peluqueria = Peluqueria.objects.create(
            nombre="Barberia Centro", ubicacion="Calle 1", telefono="300-1111",
        )
        self.admin = Usuario.objects.create(
            nombre="Root", apellido="Admin", email="root@test.com", password="x",
            rol="Admin", activo=True,
        )
        self.cliente = Usuario.objects.create(
            nombre="Ana", apellido="Gomez", email="ana@test.com", password="x",
            rol="Cliente", activo=True,
        )
        self.barbero = Usuario.objects.create(
            nombre="Luis", apellido="Rios", email="luis@test.com", password="x",
            rol="Barbero", peluqueria=self.peluqueria, activo=True,
        )
        self.pomada = Producto.objects.create(nombre="Pomada para el Cabello", precio=45900)
        self.aceite = Producto.objects.create(nombre="Aceite para Barba", precio=35900)
        self.cera = Producto.objects.create(nombre="Cera Extra", precio=28900)

    def tearDown(self):
        cache.clear()

    def sesion(self, usuario):
        s = self.client.session
        s["logueado"] = {"id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol}
        s.save()

    def resena(self, puntuacion=5, comentario="Excelente servicio"):
        """Crea una reseña real: cada una exige su propia reserva completada."""
        reserva = Reserva.objects.create(
            cliente=self.cliente, peluquero=self.barbero, peluqueria=self.peluqueria,
            fecha=date(2026, 1, 1), hora=time(10, 0),
            servicio="Corte de Cabello", estado="Completada",
        )
        return Calificacion.objects.create(
            reserva=reserva, cliente=self.cliente, barbero=self.barbero,
            puntuacion=puntuacion, comentario=comentario,
        )

    def editar(self, **datos):
        return self.client.post(reverse("sena:admin_editar_inicio"), datos)

    # ---------- El inicio muestra datos reales ----------

    def test_el_inicio_ofrece_los_servicios_y_productos_reales(self):
        r = self.client.get(reverse("sena:inicio"))
        self.assertEqual(r.status_code, 200)
        # Servicios del catálogo del sistema.
        self.assertContains(r, "Corte de Cabello")
        self.assertContains(r, "Arreglo de Barba")
        # Productos reales de la tienda (no los de antes, escritos a mano).
        self.assertContains(r, "Pomada para el Cabello")
        self.assertContains(r, "Aceite para Barba")

    def test_por_defecto_la_portada_destaca_la_pomada_y_el_aceite(self):
        # Aunque exista otro producto con un id menor, se destacan los de siempre.
        Producto.objects.create(nombre="Aaa Herramienta", precio=1000)
        r = self.client.get(reverse("sena:inicio"))
        nombres = [p.nombre for p in r.context["inicio_productos"]]
        self.assertEqual(nombres, ["Pomada para el Cabello", "Aceite para Barba"])

    def test_el_admin_puede_cambiar_los_destacados_de_la_portada(self):
        self.sesion(self.admin)
        self.editar(
            servicio_destacado_1="Combo Completo",
            servicio_destacado_2="Arreglo de Barba",
            producto_destacado_1=self.cera.id,
            producto_destacado_2=self.aceite.id,
        )
        r = self.client.get(reverse("sena:inicio") + "?vista=publica")
        nombres = [p.nombre for p in r.context["inicio_productos"]]
        self.assertEqual(nombres, ["Cera Extra", "Aceite para Barba"])

    def test_el_admin_elige_los_servicios_y_productos_destacados(self):
        self.sesion(self.admin)
        r = self.editar(
            servicio_destacado_1="Combo Completo",
            servicio_destacado_2="Corte de Cabello",
            producto_destacado_1=self.cera.id,
            producto_destacado_2=self.pomada.id,
        )
        self.assertEqual(r.status_code, 302)
        config = Configuracion.cargar()
        self.assertEqual(config.servicio_destacado_1, "Combo Completo")
        self.assertEqual(config.servicio_destacado_2, "Corte de Cabello")
        self.assertEqual(config.producto_destacado_1, self.cera)
        self.assertEqual(config.producto_destacado_2, self.pomada)
        # Y se refleja en la página principal (el Admin la ve con ?vista=publica).
        r = self.client.get(reverse("sena:inicio") + "?vista=publica")
        self.assertContains(r, "Combo Completo")
        self.assertContains(r, "Cera Extra")

    def test_no_se_pueden_destacar_servicios_productos_inexistentes(self):
        self.sesion(self.admin)
        self.editar(
            servicio_destacado_1="Servicio Fantasma",
            servicio_destacado_2="Otro Inventado",
            producto_destacado_1="999999",
            producto_destacado_2="",
        )
        config = Configuracion.cargar()
        self.assertEqual(config.servicio_destacado_1, "")
        self.assertEqual(config.servicio_destacado_2, "")
        self.assertIsNone(config.producto_destacado_1)
        self.assertIsNone(config.producto_destacado_2)
        # El inicio sigue completo, con los valores automáticos.
        r = self.client.get(reverse("sena:inicio") + "?vista=publica")
        self.assertContains(r, "Corte de Cabello")

    def test_el_admin_ve_el_formulario_del_inicio(self):
        self.sesion(self.admin)
        r = self.client.get(reverse("sena:admin_editar_inicio"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Editar el")
        self.assertContains(r, "Servicios destacados")
        self.assertContains(r, "Productos destacados")

    def test_el_mismo_servicio_elegido_dos_veces_no_se_repite(self):
        self.sesion(self.admin)
        self.editar(
            servicio_destacado_1="Combo Completo",
            servicio_destacado_2="Combo Completo",
        )
        r = self.client.get(reverse("sena:inicio") + "?vista=publica")
        self.assertEqual(r.status_code, 200)
        # El servicio repetido aparece una sola vez y el hueco se completa solo.
        nombres = [s["nombre"] for s in r.context["inicio_servicios"]]
        self.assertEqual(nombres, ["Combo Completo", "Corte de Cabello"])

    # ---------- Solo el Admin ----------

    def test_solo_el_admin_edita_el_inicio(self):
        # Sin sesión va al login.
        r = self.client.get(reverse("sena:admin_editar_inicio"))
        self.assertEqual(r.status_code, 302)
        # Un cliente tampoco entra ni puede guardar.
        self.sesion(self.cliente)
        r = self.client.get(reverse("sena:admin_editar_inicio"))
        self.assertEqual(r.status_code, 302)
        self.editar(servicio_destacado_1="Combo Completo")
        self.assertEqual(Configuracion.cargar().servicio_destacado_1, "")

    def test_al_admin_lo_llevan_a_su_panel_pero_puede_ver_el_inicio(self):
        # Un visitante anónimo nunca ve el botón de editar.
        r = self.client.get(reverse("sena:inicio"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Editar inicio")

        self.sesion(self.admin)
        # Por defecto el Admin va a su panel, no al inicio público.
        r = self.client.get(reverse("sena:inicio"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("sena:admin_dashboard"), r.url)
        # Con ?vista=publica sí lo ve, y con el botón de editar.
        r = self.client.get(reverse("sena:inicio") + "?vista=publica")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Editar inicio")

    # ---------- Reseñas reales ----------

    def test_sin_resenas_muestra_un_aviso_amable(self):
        r = self.client.get(reverse("sena:inicio"))
        self.assertContains(r, "Todavía no hay reseñas")
        self.assertNotContains(r, "Ver más reseñas")

    def test_las_resenas_reales_aparecen_en_el_inicio(self):
        self.resena(puntuacion=5, comentario="Excelente servicio")
        r = self.client.get(reverse("sena:inicio"))
        self.assertContains(r, "Excelente servicio")
        # Se muestra el nombre con la inicial del apellido, no el apellido entero.
        self.assertContains(r, "Ana G.")
        self.assertNotContains(r, "Todavía no hay reseñas")

    def test_con_mas_de_cinco_resenas_aparece_ver_mas(self):
        for i in range(RESENAS_VISIBLES + 2):
            self.resena(comentario=f"Reseña numero {i}")
        r = self.client.get(reverse("sena:inicio"))
        self.assertContains(r, "Ver más reseñas")
        # Todas viajan en la página; las extra quedan ocultas hasta pulsar el botón.
        for i in range(RESENAS_VISIBLES + 2):
            self.assertContains(r, f"Reseña numero {i}")
        self.assertEqual(r.content.decode().count("hidden data-resena-extra"), 2)

    def test_con_cinco_resenas_o_menos_no_hay_ver_mas(self):
        for i in range(RESENAS_VISIBLES):
            self.resena(comentario=f"Reseña numero {i}")
        r = self.client.get(reverse("sena:inicio"))
        self.assertNotContains(r, "Ver más reseñas")
        self.assertEqual(r.content.decode().count("hidden data-resena-extra"), 0)

    def test_las_resenas_no_se_publican_si_el_admin_lo_desactiva(self):
        config = Configuracion.cargar()
        config.mostrar_calificaciones = False
        config.save()
        self.resena(comentario="No deberia verse")
        r = self.client.get(reverse("sena:inicio"))
        self.assertNotContains(r, "No deberia verse")
        self.assertContains(r, "Todavía no hay reseñas")


class LimiteDeResenasTests(TestCase):
    """Cada cliente puede publicar como máximo dos reseñas."""

    def setUp(self):
        cache.clear()
        self.peluqueria = Peluqueria.objects.create(
            nombre="Barberia Centro", ubicacion="Calle 1", telefono="300-1111",
        )
        self.cliente = Usuario.objects.create(
            nombre="Ana", apellido="Gomez", email="ana@test.com", password="x",
            rol="Cliente", activo=True,
        )
        self.barbero = Usuario.objects.create(
            nombre="Luis", apellido="Rios", email="luis@test.com", password="x",
            rol="Barbero", peluqueria=self.peluqueria, activo=True,
        )
        # Tres citas completadas sin calificar
        self.citas = [
            Reserva.objects.create(
                cliente=self.cliente, peluquero=self.barbero, peluqueria=self.peluqueria,
                fecha=date(2026, 1, i + 1), hora=time(10, 0),
                servicio="Corte de Cabello", estado="Completada",
            )
            for i in range(3)
        ]

    def tearDown(self):
        cache.clear()

    def sesion(self):
        s = self.client.session
        s["logueado"] = {"id": self.cliente.id, "nombre": self.cliente.nombre, "rol": "Cliente"}
        s.save()

    def calificar(self, reserva):
        return self.client.post(
            reverse("sena:usuario_calificar", args=[reserva.id]),
            {"puntuacion": 5, "comentario": "Muy bueno"},
        )

    def test_solo_dos_resenas_por_cliente(self):
        self.sesion()
        self.calificar(self.citas[0])
        self.calificar(self.citas[1])
        self.assertEqual(Calificacion.objects.filter(cliente=self.cliente).count(), 2)

        self.calificar(self.citas[2])  # La tercera ya no se guarda
        self.assertEqual(Calificacion.objects.filter(cliente=self.cliente).count(), 2)

    def test_al_llegar_al_limite_desaparece_la_opcion_de_calificar(self):
        self.sesion()
        r = self.client.get(reverse("sena:usuario_perfil"))
        self.assertEqual(r.context["resenas_restantes"], 2)  # Cupo completo
        self.assertContains(r, "Califica esta cita")

        self.calificar(self.citas[0])
        self.calificar(self.citas[1])
        r = self.client.get(reverse("sena:usuario_perfil"))
        self.assertEqual(r.context["resenas_restantes"], 0)
        self.assertContains(r, "Ya usaste tus 2 reseñas permitidas")
        self.assertNotContains(r, "Califica esta cita")

    def test_el_limite_es_por_cliente(self):
        otro = Usuario.objects.create(
            nombre="Beto", apellido="Lopez", email="beto@test.com", password="x",
            rol="Cliente", activo=True,
        )
        Reserva.objects.create(
            cliente=otro, peluquero=self.barbero, peluqueria=self.peluqueria,
            fecha=date(2026, 2, 1), hora=time(11, 0),
            servicio="Corte de Cabello", estado="Completada",
        )
        Calificacion.objects.create(
            reserva=self.citas[0], cliente=self.cliente, barbero=self.barbero,
            puntuacion=5, comentario="Buena",
        )
        Calificacion.objects.create(
            reserva=self.citas[1], cliente=self.cliente, barbero=self.barbero,
            puntuacion=4, comentario="Buena",
        )
        s = self.client.session
        s["logueado"] = {"id": otro.id, "nombre": otro.nombre, "rol": "Cliente"}
        s.save()
        r = self.client.get(reverse("sena:usuario_perfil"))
        self.assertEqual(r.context["resenas_restantes"], 2)  # Su propio cupo sigue libre

