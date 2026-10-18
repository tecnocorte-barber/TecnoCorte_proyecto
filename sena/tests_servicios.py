# Pruebas del flujo de servicios propios: el barbero solicita y el Admin lo crea.
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Notificacion, Peluqueria, Servicio, SolicitudServicio, Usuario
from .views import catalogo_servicios, minutos_servicio, servicio_valido


class ServiciosDeBarberoTests(TestCase):
    def setUp(self):
        self.peluqueria = Peluqueria.objects.create(
            nombre="Barberia Centro", ubicacion="Calle 1", telefono="300-1111",
        )
        self.barbero = Usuario.objects.create(
            nombre="Luis", apellido="Rios", email="luis@test.com", password="x",
            rol="Barbero", peluqueria=self.peluqueria, activo=True,
        )
        self.otro_barbero = Usuario.objects.create(
            nombre="Pedro", apellido="Perez", email="pedro@test.com", password="x",
            rol="Barbero", peluqueria=self.peluqueria, activo=True,
        )
        self.admin = Usuario.objects.create(
            nombre="Root", apellido="Admin", email="root@test.com", password="x",
            rol="Admin", activo=True,
        )

    def tearDown(self):
        cache.clear()

    def sesion(self, usuario):
        s = self.client.session
        s["logueado"] = {"id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol}
        s.save()

    def solicitar(self, nombre="Afeitado Premium", minutos="30", precio="25000"):
        return self.client.post(reverse("sena:peluquero_configuracion"), {
            "accion": "solicitar_servicio",
            "nombre": nombre, "descripcion": "Con toalla caliente",
            "minutos": minutos, "precio": precio,
        })

    # ---------- El barbero solicita, no crea ----------

    def test_el_barbero_envia_una_solicitud_sin_crear_el_servicio(self):
        self.sesion(self.barbero)
        r = self.solicitar()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SolicitudServicio.objects.count(), 1)
        solicitud = SolicitudServicio.objects.get()
        self.assertEqual(solicitud.estado, "pendiente")
        self.assertEqual(solicitud.nombre, "Afeitado Premium")
        self.assertEqual(solicitud.minutos, 30)
        self.assertEqual(solicitud.precio, 25000)
        # Todavía no existe como servicio real.
        self.assertFalse(Servicio.objects.exists())

    def test_el_admin_recibe_aviso_de_la_solicitud(self):
        self.sesion(self.barbero)
        self.solicitar()
        aviso = Notificacion.objects.filter(usuario=self.admin)
        self.assertTrue(aviso.exists())
        self.assertIn("Afeitado Premium", aviso.first().mensaje)

    def test_solicitudes_invalidas_no_se_guardan(self):
        self.sesion(self.barbero)
        # Nombre vacío.
        self.solicitar(nombre="")
        # Duración fuera de la lista permitida.
        self.solicitar(nombre="Servicio Malo", minutos="7")
        # Precio no numérico.
        self.solicitar(nombre="Servicio Caro", precio="mucho")
        # Un servicio que ya es del sistema no se pide.
        self.solicitar(nombre="Corte de Cabello")
        self.assertEqual(SolicitudServicio.objects.count(), 0)

    def test_no_se_duplican_solicitudes_ni_servicios_propios(self):
        self.sesion(self.barbero)
        self.solicitar()
        self.solicitar()  # Repetida: no crea otra pendiente
        self.assertEqual(SolicitudServicio.objects.count(), 1)
        # Si ya lo ofrece, tampoco deja pedirlo otra vez.
        Servicio.objects.create(nombre="Afeitado Premium", barbero=self.barbero, precio=25000)
        self.solicitar()
        self.assertEqual(SolicitudServicio.objects.count(), 1)

    def test_el_barbero_puede_cancelar_su_solicitud_pendiente(self):
        self.sesion(self.barbero)
        self.solicitar()
        solicitud = SolicitudServicio.objects.get()
        self.client.post(reverse("sena:peluquero_configuracion"), {
            "accion": "cancelar_solicitud", "solicitud_id": solicitud.id,
        })
        self.assertFalse(SolicitudServicio.objects.exists())

    def test_no_puede_cancelar_la_solicitud_de_otro(self):
        solicitud = SolicitudServicio.objects.create(
            barbero=self.otro_barbero, nombre="De Pedro", minutos=30, precio=1000,
        )
        self.sesion(self.barbero)
        self.client.post(reverse("sena:peluquero_configuracion"), {
            "accion": "cancelar_solicitud", "solicitud_id": solicitud.id,
        })
        self.assertTrue(SolicitudServicio.objects.filter(id=solicitud.id).exists())

    # ---------- El Admin aprueba o rechaza ----------

    def test_el_admin_aprueba_y_crea_el_servicio_para_ese_barbero(self):
        solicitud = SolicitudServicio.objects.create(
            barbero=self.barbero, nombre="Afeitado Premium", descripcion="d",
            duracion="30 Minutos", minutos=30, precio=25000,
        )
        self.sesion(self.admin)
        r = self.client.post(reverse("sena:admin_solicitudes_servicios"), {
            "accion": "aprobar", "solicitud_id": solicitud.id, "nota_admin": "Bien",
        })
        self.assertEqual(r.status_code, 302)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "aprobada")
        self.assertIsNotNone(solicitud.resuelta)
        servicio = Servicio.objects.get(nombre="Afeitado Premium")
        self.assertEqual(servicio.barbero, self.barbero)
        self.assertEqual(servicio.peluqueria, self.peluqueria)
        self.assertEqual(servicio.minutos, 30)
        self.assertEqual(servicio.precio, 25000)
        # El barbero recibe la buena noticia.
        self.assertTrue(Notificacion.objects.filter(usuario=self.barbero).exists())

    def test_el_admin_rechaza_con_nota_y_no_crea_nada(self):
        solicitud = SolicitudServicio.objects.create(
            barbero=self.barbero, nombre="Afeitado Premium", minutos=30, precio=25000,
        )
        self.sesion(self.admin)
        self.client.post(reverse("sena:admin_solicitudes_servicios"), {
            "accion": "rechazar", "solicitud_id": solicitud.id, "nota_admin": "Precio muy bajo",
        })
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "rechazada")
        self.assertEqual(solicitud.nota_admin, "Precio muy bajo")
        self.assertFalse(Servicio.objects.exists())
        aviso = Notificacion.objects.filter(usuario=self.barbero).first()
        self.assertIn("Precio muy bajo", aviso.mensaje)

    def test_una_solicitud_ya_resuelta_no_se_vuelve_a_resolver(self):
        solicitud = SolicitudServicio.objects.create(
            barbero=self.barbero, nombre="Afeitado Premium", minutos=30, precio=25000,
            estado="rechazada",
        )
        self.sesion(self.admin)
        self.client.post(reverse("sena:admin_solicitudes_servicios"), {
            "accion": "aprobar", "solicitud_id": solicitud.id,
        })
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "rechazada")
        self.assertFalse(Servicio.objects.exists())

    def test_solo_el_admin_entra_a_las_solicitudes(self):
        self.sesion(self.barbero)
        r = self.client.get(reverse("sena:admin_solicitudes_servicios"))
        self.assertEqual(r.status_code, 302)
        # Un barbero tampoco puede aprobar por POST.
        solicitud = SolicitudServicio.objects.create(
            barbero=self.barbero, nombre="Afeitado Premium", minutos=30, precio=25000,
        )
        self.client.post(reverse("sena:admin_solicitudes_servicios"), {
            "accion": "aprobar", "solicitud_id": solicitud.id,
        })
        self.assertFalse(Servicio.objects.exists())
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "pendiente")

    # ---------- El servicio aprobado entra al catálogo de reservas ----------

    def test_el_servicio_aprobado_entra_al_catalogo_y_a_la_reserva(self):
        Servicio.objects.create(
            nombre="Afeitado Premium", descripcion="d", duracion="30 Minutos",
            minutos=30, precio=25000, barbero=self.barbero, peluqueria=self.peluqueria,
        )
        nombres = {item["nombre"] for item in catalogo_servicios()}
        self.assertIn("Afeitado Premium", nombres)
        self.assertIn("Corte de Cabello", nombres)  # Los base siguen ahí
        self.assertEqual(minutos_servicio("Afeitado Premium"), 30)
        self.assertTrue(servicio_valido("Afeitado Premium"))
        self.assertFalse(servicio_valido("Servicio Que No Existe"))

        # La reserva del cliente ya lo ofrece y permite preseleccionarlo.
        r = self.client.get(
            reverse("sena:usuario_reservar_cita") + "?servicio=Afeitado%20Premium"
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["servicio_inicial"], "Afeitado Premium")
        self.assertContains(r, "Afeitado Premium")

    def test_un_servicio_inactivo_no_aparece(self):
        Servicio.objects.create(nombre="Retirado", barbero=self.barbero, activo=False, minutos=45)
        self.assertFalse(servicio_valido("Retirado"))
        self.assertNotIn("Retirado", {i["nombre"] for i in catalogo_servicios()})

    # ---------- Paneles ----------

    def test_la_pestana_de_servicios_del_barbero_ofrece_el_formulario(self):
        self.sesion(self.barbero)
        r = self.client.get(reverse("sena:peluquero_configuracion") + "?seccion=servicios")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Solicitar un servicio nuevo")
        self.assertContains(r, "Mis solicitudes")
        # Sin servicios propios, la sección de "Tus servicios propios" no aparece.
        self.assertNotContains(r, "Tus servicios propios")
        # Al tener uno aprobado, sí se muestra.
        Servicio.objects.create(nombre="Afeitado Premium", barbero=self.barbero, minutos=30, precio=25000)
        r = self.client.get(reverse("sena:peluquero_configuracion") + "?seccion=servicios")
        self.assertContains(r, "Tus servicios propios")
        self.assertContains(r, "Afeitado Premium")

    def test_la_pagina_del_admin_lista_las_solicitudes(self):
        SolicitudServicio.objects.create(
            barbero=self.barbero, nombre="Afeitado Premium", minutos=30, precio=25000,
        )
        self.sesion(self.admin)
        r = self.client.get(reverse("sena:admin_solicitudes_servicios"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Afeitado Premium")
        self.assertContains(r, "Aprobar y crear")
        self.assertContains(r, "Luis")

    # ---------- Las tablas no se enciman una sobre otra (regresión) ----------

    def test_las_tablas_del_admin_van_apiladas_y_no_superpuestas(self):
        SolicitudServicio.objects.create(
            barbero=self.barbero, nombre="Afeitado Premium", minutos=30,
            precio=25000, estado="rechazada",
        )
        self.sesion(self.admin)
        r = self.client.get(reverse("sena:admin_solicitudes_servicios"))
        # Las dos tablas viven en una columna con aire entre ellas...
        self.assertContains(r, 'class="tc-stack"')
        self.assertEqual(r.content.decode().count("table-responsive"), 2)
        # ...y NO dentro del contenedor fijo del menú lateral, que era lo que
        # las sacaba del flujo y las montaba encima de la siguiente.
        self.assertNotContains(r, "panel-glass overflow-hidden")

    def test_la_pestana_de_servicios_del_barbero_usa_la_caja_con_scroll(self):
        self.sesion(self.barbero)
        r = self.client.get(reverse("sena:peluquero_configuracion") + "?seccion=servicios")
        self.assertContains(r, "table-responsive")
        self.assertNotContains(r, "panel-glass overflow-hidden")
