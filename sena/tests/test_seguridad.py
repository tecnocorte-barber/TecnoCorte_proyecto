# Pruebas de seguridad: páginas de error, aviso al Admin, enlaces y permisos.
import os
import tempfile
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, include, path, reverse

from ..models import MensajeContacto, Notificacion, RegistroError, Usuario
from ..views import _json_seguro


# ── URLconf de prueba ───────────────────────────────────────────────────────
# Se usa como ROOT_URLCONF en las pruebas de error para poder provocar un fallo
# real sin tocar el código de producción.
def vista_que_revienta(request):
    raise RuntimeError("fallo interno provocado en la prueba")


def vista_prohibida(request):
    raise PermissionDenied("sección reservada")


urlpatterns = [
    path("", include("sena.urls")),
    path("__prueba__/revienta/", vista_que_revienta, name="prueba_revienta"),
    path("__prueba__/prohibida/", vista_prohibida, name="prueba_prohibida"),
]

# Al sustituir ROOT_URLCONF hay que declarar otra vez los handlers: Django los
# lee del módulo de urls que esté activo, no del original.
handler404 = "sena.errores.pagina_no_encontrada"
handler403 = "sena.errores.pagina_prohibida"
handler500 = "sena.errores.error_servidor"


# Config mínima para que se ejecute el handler500: Django solo lo usa con
# DEBUG=False, y en ese modo las cookies y la redirección SSL no aplican al test.
AJUSTES_PRODUCCION = {
    "DEBUG": False,
    "ALLOWED_HOSTS": ["testserver", "localhost", "127.0.0.1"],
    "SECURE_SSL_REDIRECT": False,
    "SESSION_COOKIE_SECURE": False,
    "CSRF_COOKIE_SECURE": False,
    "ROOT_URLCONF": "sena.tests.test_seguridad",
}


class OperationalErrorSimulado(Exception):
    """Simula una base de datos caída."""


@override_settings(**AJUSTES_PRODUCCION)
class PaginasDeErrorTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create(
            nombre="Admin", apellido="Uno", email="admin.error@test.com",
            password="x", rol="Admin", activo=True,
        )

    def _sin_captura(self):
        """Cliente que no relanza la excepción: el handler500 ya la convierte en página."""
        from django.test import Client

        return Client(raise_request_exception=False)

    # ── 404 ──

    def test_la_ruta_inexistente_muestra_la_pagina_amigable(self):
        r = self.client.get("/no-existe-esta-seccion/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Estamos teniendo problemas", status_code=404)
        self.assertContains(r, "Nuestro equipo ya recibió el aviso", status_code=404)
        # No debe verse ni el traceback ni el detalle técnico de Django.
        self.assertNotContains(r, "Traceback", status_code=404)
        self.assertNotContains(r, "Django tried these URL patterns", status_code=404)
        self.assertNotContains(r, "DEBUG = True", status_code=404)

    def test_el_404_avisa_igual_que_el_500(self):
        """Un enlace roto y un fallo interno muestran la misma tarjeta."""
        r404 = self.client.get("/no-existe-esta-seccion/")
        r500 = self._sin_captura().get("/__prueba__/revienta/")
        for respuesta, estado in ((r404, 404), (r500, 500)):
            self.assertContains(respuesta, "Estamos teniendo problemas", status_code=estado)
            self.assertContains(
                respuesta, "Nuestro equipo ya recibió el aviso de este fallo", status_code=estado
            )

    def test_el_404_ofrece_un_codigo_para_reportar(self):
        r = self.client.get("/no-existe-esta-seccion/")
        registro = RegistroError.objects.get(codigo_http=404)
        self.assertContains(r, registro.codigo, status_code=404)

    def test_el_404_se_registra_pero_no_alarma_al_admin(self):
        """Los enlaces rotos quedan registrados sin llenar la bandeja de avisos.

        Los rastreadores generan 404 sin parar: si cada uno notificara, el
        Admin dejaría de ver las alertas importantes.
        """
        Notificacion.objects.all().delete()
        MensajeContacto.objects.all().delete()
        self.client.get("/no-existe-esta-seccion/")
        self.assertTrue(RegistroError.objects.filter(codigo_http=404).exists())
        self.assertFalse(Notificacion.objects.exists())
        self.assertFalse(MensajeContacto.objects.filter(nombre="Sistema TecnoCorte").exists())

    # ── 403 ──

    def test_un_error_de_permisos_tambien_es_amigable(self):
        r = self.client.get("/__prueba__/prohibida/")
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, "No tienes permiso", status_code=403)
        self.assertNotContains(r, "Traceback", status_code=403)

    # ── 500 ──

    def test_un_fallo_inesperado_muestra_el_mensaje_centrado(self):
        r = self._sin_captura().get("/__prueba__/revienta/")
        self.assertEqual(r.status_code, 500)
        self.assertContains(r, "Estamos teniendo problemas", status_code=500)
        self.assertContains(r, "Nuestro equipo ya recibió el aviso", status_code=500)

    def test_el_500_no_filtra_ni_el_tipo_ni_el_texto_del_fallo(self):
        r = self._sin_captura().get("/__prueba__/revienta/")
        self.assertNotContains(r, "fallo interno provocado en la prueba", status_code=500)
        self.assertNotContains(r, "Traceback", status_code=500)
        self.assertNotContains(r, "RuntimeError", status_code=500)
        self.assertNotContains(r, "site-packages", status_code=500)
        self.assertNotContains(r, "DEBUG = True", status_code=500)

    def test_el_500_queda_registrado_con_la_traza_para_el_admin(self):
        self._sin_captura().get("/__prueba__/revienta/")
        registro = RegistroError.objects.filter(codigo_http=500).first()
        self.assertIsNotNone(registro)
        self.assertEqual(registro.tipo, "RuntimeError")
        self.assertIn("fallo interno provocado en la prueba", registro.mensaje)
        # La traza sí queda guardada, para poder reproducir el fallo.
        self.assertIn("vista_que_revienta", registro.detalle)
        self.assertEqual(registro.ruta, "/__prueba__/revienta/")

    def test_el_500_no_crea_notificacion_y_se_consulta_en_errores(self):
        Notificacion.objects.all().delete()
        MensajeContacto.objects.all().delete()
        self._sin_captura().get("/__prueba__/revienta/")

        notificacion = Notificacion.objects.filter(usuario=self.admin).first()
        self.assertIsNone(notificacion)

        self.assertFalse(MensajeContacto.objects.filter(nombre="Sistema TecnoCorte").exists())

    def test_el_codigo_que_ve_la_persona_coincide_con_el_registro(self):
        r = self._sin_captura().get("/__prueba__/revienta/")
        registro = RegistroError.objects.filter(codigo_http=500).first()
        self.assertIsNotNone(registro)
        self.assertContains(r, registro.codigo, status_code=500)

    # ── Robustez ──

    def test_la_pagina_de_error_se_renderiza_aunque_cae_la_base_de_datos(self):
        """El motor 'errores' no usa procesadores de contexto, que sí tocan la BD."""
        with mock.patch(
            "sena.context_processors.Configuracion.cargar",
            side_effect=OperationalErrorSimulado(),
        ):
            r = self.client.get("/no-existe-esta-seccion/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Estamos teniendo problemas", status_code=404)

    def test_el_registro_de_errores_no_rompe_si_falla_la_base(self):
        """Si no se puede guardar, la persona igual ve la página amigable."""
        with mock.patch.object(
            RegistroError.objects, "create", side_effect=OperationalErrorSimulado()
        ):
            r = self._sin_captura().get("/__prueba__/revienta/")
        self.assertEqual(r.status_code, 500)
        self.assertContains(r, "Estamos teniendo problemas", status_code=500)

    # ── Detalle técnico solo para el Admin ──

    def _como_admin(self):
        cliente = self._sin_captura()
        sesion = cliente.session
        sesion["logueado"] = {
            "id": self.admin.id,
            "rol": "Admin",
            "nombre": self.admin.nombre,
            "sesion_version": self.admin.sesion_version,
        }
        sesion.save()
        return cliente

    def test_el_admin_ve_el_tipo_de_error_en_la_tarjeta(self):
        r = self._como_admin().get("/__prueba__/revienta/")
        self.assertEqual(r.status_code, 500)
        self.assertContains(r, "Detalle para administradores", status_code=500)
        self.assertContains(r, "RuntimeError", status_code=500)
        self.assertContains(r, "/__prueba__/revienta/", status_code=500)

    def test_quien_no_es_admin_no_ve_el_detalle_tecnico(self):
        r = self.client.get("/no-existe-esta-seccion/")
        self.assertNotContains(r, "Detalle para administradores", status_code=404)
        self.assertNotContains(r, "Http404", status_code=404)


@override_settings(
    DEBUG=True,
    ROOT_URLCONF="sena.tests.test_seguridad",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class TarjetaDeErrorEnDesarrolloTests(TestCase):
    """Con DEBUG encendido, Django pone su página amarilla; el middleware la evita."""

    def setUp(self):
        self.admin = Usuario.objects.create(
            nombre="Admin", apellido="Dos", email="admin.debug@test.com",
            password="x", rol="Admin", activo=True,
        )

    def _sin_captura(self):
        from django.test import Client

        return Client(raise_request_exception=False)

    def test_un_enlace_roto_no_muestra_las_rutas_que_probo_django(self):
        r = self.client.get("/usuario/error/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Estamos teniendo problemas", status_code=404)
        self.assertNotContains(r, "Django tried these URL patterns", status_code=404)
        self.assertNotContains(r, "DEBUG = True", status_code=404)

    def test_un_fallo_tampoco_muestra_la_pantalla_amarilla(self):
        r = self._sin_captura().get("/__prueba__/revienta/")
        self.assertEqual(r.status_code, 500)
        self.assertContains(r, "Estamos teniendo problemas", status_code=500)
        self.assertNotContains(r, "RuntimeError", status_code=500)
        self.assertNotContains(r, "Traceback", status_code=500)
        # El fallo se registra igual que en producción.
        registro = RegistroError.objects.filter(codigo_http=500).first()
        self.assertIsNotNone(registro)
        self.assertEqual(registro.tipo, "RuntimeError")
        self.assertIn("vista_que_revienta", registro.detalle)

    def test_el_admin_sigue_viendo_el_tipo_con_debug_encendido(self):
        cliente = self.client
        sesion = cliente.session
        sesion["logueado"] = {
            "id": self.admin.id,
            "rol": "Admin",
            "nombre": self.admin.nombre,
            "sesion_version": self.admin.sesion_version,
        }
        sesion.save()
        r = cliente.get("/usuario/error/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Detalle para administradores", status_code=404)
        self.assertContains(r, "Http404", status_code=404)
        self.assertContains(r, "/usuario/error/", status_code=404)

    def test_las_rutas_de_la_api_conservan_su_respuesta(self):
        """La API responde JSON: sustituirla por la tarjeta rompería al cliente."""
        r = self.client.get("/api/no-existe-esta-ruta/")
        self.assertEqual(r.status_code, 404)
        self.assertNotContains(r, "Estamos teniendo problemas", status_code=404)


class PaginaDeErroresDelAdminTests(TestCase):
    """El Admin revisa los fallos desde el panel, sin entrar al admin de Django."""

    def setUp(self):
        # El contador del panel vive en caché: se limpia para que cada prueba parta de cero.
        cache.clear()
        self.admin = Usuario.objects.create(
            nombre="Admin", apellido="Tres", email="admin.lista.errores@test.com",
            password="x", rol="Admin", activo=True,
        )
        self.fallo = RegistroError.objects.create(
            codigo="E-PRUEBA1", codigo_http=500, ruta="/__prueba__/revienta/", metodo="GET",
            tipo="RuntimeError", mensaje="fallo interno provocado en la prueba",
            detalle="Traceback (most recent call last):\n  vista_que_revienta",
            ip="127.0.0.1",
        )

    def _como_admin(self):
        from django.test import Client

        cliente = Client()
        sesion = cliente.session
        sesion["logueado"] = {
            "id": self.admin.id,
            "rol": "Admin",
            "nombre": self.admin.nombre,
            "sesion_version": self.admin.sesion_version,
        }
        sesion.save()
        return cliente

    def test_solo_el_admin_entra_a_la_lista(self):
        r = self.client.get("/admin/errores/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_la_lista_muestra_tipo_ruta_traza_y_el_enlace_del_panel(self):
        r = self._como_admin().get("/admin/errores/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "RuntimeError")
        self.assertContains(r, "/__prueba__/revienta/")
        self.assertContains(r, "E-PRUEBA1")
        self.assertContains(r, "vista_que_revienta")
        self.assertContains(r, 'href="/admin/errores/"')
        self.assertContains(r, "Sin revisar")

    def test_el_admin_marca_el_fallo_como_revisado(self):
        r = self._como_admin().post(
            "/admin/errores/", {"registro_id": self.fallo.id, "estado": "revisado"}
        )
        self.assertEqual(r.status_code, 302)
        self.fallo.refresh_from_db()
        self.assertEqual(self.fallo.estado, "revisado")
        self.assertContains(self._como_admin().get("/admin/errores/"), "Revisado")

    def test_un_estado_inventado_no_cambia_nada(self):
        self._como_admin().post(
            "/admin/errores/", {"registro_id": self.fallo.id, "estado": "inventado"}
        )
        self.fallo.refresh_from_db()
        self.assertEqual(self.fallo.estado, "pendiente")

    def test_el_admin_marca_todos_los_fallos_como_revisados(self):
        segundo = RegistroError.objects.create(
            codigo="E-PRUEBA2", codigo_http=404, ruta="/otra-ruta/", metodo="GET",
            tipo="Http404", mensaje="sin página", ip="127.0.0.1",
        )
        r = self._como_admin().post("/admin/errores/", {"accion": "revisar_todos"})
        self.assertEqual(r.status_code, 302)
        self.fallo.refresh_from_db()
        segundo.refresh_from_db()
        self.assertEqual(self.fallo.estado, "revisado")
        self.assertEqual(segundo.estado, "revisado")
        self.assertEqual(
            self._como_admin().get("/admin/errores/").context["errores_pendientes"], 0
        )

    def test_el_panel_avisa_cuantos_fallos_quedan_sin_revisar(self):
        r = self._como_admin().get("/admin/errores/")
        self.assertEqual(r.context["errores_pendientes"], 1)

    def test_el_aviso_baja_al_marcar_el_fallo(self):
        self._como_admin().get("/admin/errores/")  # deja el contador en caché
        self._como_admin().post(
            "/admin/errores/", {"registro_id": self.fallo.id, "estado": "revisado"}
        )
        r = self._como_admin().get("/admin/errores/")
        self.assertEqual(r.context["errores_pendientes"], 0)


# ── Auditorías que deben seguir cumpliéndose ────────────────────────────────
class AuditoriaDeEnlacesTests(TestCase):
    def test_todos_los_url_de_las_plantillas_existen(self):
        """Ninguna plantilla apunta a una url name inexistente."""
        import io
        import os
        import re

        from django.urls import get_resolver

        nombres = set()

        def recorrer(resolver, ns=""):
            for nombre in resolver.reverse_dict.keys():
                nombres.add("%s:%s" % (ns, nombre) if ns else str(nombre))
            for sub in resolver.url_patterns:
                if hasattr(sub, "url_patterns"):
                    recorrer(sub, getattr(sub, "namespace", None) or ns)

        recorrer(get_resolver())

        base = os.path.join(settings.BASE_DIR, "sena", "templates")
        rotos = []
        for raiz, _, archivos in os.walk(base):
            for archivo in archivos:
                if not archivo.endswith(".html"):
                    continue
                ruta = os.path.join(raiz, archivo)
                texto = io.open(ruta, encoding="utf-8", errors="replace").read()
                for numero, linea in enumerate(texto.splitlines(), 1):
                    for m in re.finditer(r"\{%\s*url\s+['\"]([^'\"]+)['\"]", linea):
                        if m.group(1) not in nombres:
                            rotos.append("%s:%d -> %s" % (ruta, numero, m.group(1)))
        self.assertEqual(rotos, [], "Hay enlaces a urls que no existen:\n" + "\n".join(rotos))

    def test_ningun_enlace_apunta_a_un_destino_vacio(self):
        import io
        import os
        import re

        base = os.path.join(settings.BASE_DIR, "sena", "templates")
        malos = []
        for raiz, _, archivos in os.walk(base):
            for archivo in archivos:
                if not archivo.endswith(".html"):
                    continue
                ruta = os.path.join(raiz, archivo)
                texto = io.open(ruta, encoding="utf-8", errors="replace").read()
                # El JavaScript se salta entero: ahí href='' es un patrón de
                # concatenación ('<a href="' + url), no un enlace roto.
                texto = re.sub(r"<script\b[^>]*>.*?</script>", "", texto, flags=re.S | re.I)
                for numero, linea in enumerate(texto.splitlines(), 1):
                    for m in re.finditer(r'href\s*=\s*(["\'])\s*\1', linea):
                        malos.append("%s:%d" % (ruta, numero))
        self.assertEqual(malos, [], "Hay href vacíos en: " + ", ".join(malos))


class AuditoriaDePermisosTests(TestCase):
    # Vistas públicas por diseño: no llevan @autorizacion y son correctas.
    VISTAS_PUBLICAS = {
        "inicio", "login", "solicitar_recuperacion", "restablecer_password",
        "registro", "verificar_correo", "reenviar_verificacion", "logout", "como_funciona", "sobre_nosotros", "politicas", "health_check",
        "ayuda", "carrito", "agregar_carrito", "actualizar_carrito",
        "eliminar_carrito", "usuario_dashboard", "usuario_tienda",
        "usuario_servicios", "usuario_peluquerias", "usuario_peluqueria_detalle",
        "usuario_reservar_cita", "usuario_producto_detalle",
    }

    def test_toda_vista_de_panel_tiene_autorizacion(self):
        """Toda vista propia del proyecto debe declarar sus roles o ser pública."""
        from django.urls import get_resolver

        sin_control = []

        def recorrer(resolver):
            for patron in resolver.url_patterns:
                if hasattr(patron, "url_patterns"):
                    recorrer(patron)
                    continue
                vista = getattr(patron, "callback", None)
                if vista is None or getattr(vista, "__module__", "") != "sena.views":
                    continue
                nombre = getattr(vista, "__name__", "")
                if hasattr(vista, "roles_permitidas"):
                    self.assertTrue(
                        vista.roles_permitidas,
                        "La vista %s usa @autorizacion sin roles." % nombre,
                    )
                elif nombre not in self.VISTAS_PUBLICAS:
                    sin_control.append(nombre)

        recorrer(get_resolver())
        self.assertEqual(
            sin_control, [],
            "Estas vistas no tienen @autorizacion ni están en la lista de públicas: %s"
            % ", ".join(sorted(set(sin_control))),
        )


class JsonSeguroTests(TestCase):
    def test_escapa_el_cierre_de_etiqueta(self):
        datos = {"motivo": "</script><img src=x onerror=alert(1)>"}
        salida = _json_seguro(datos)
        self.assertNotIn("</script>", salida)
        self.assertNotIn("<img", salida)
        self.assertIn("\\u003c", salida)

    def test_escapa_los_separadores_de_linea_de_unicode(self):
        salida = _json_seguro({"x": "a\u2028b\u2029c"})
        self.assertNotIn("\u2028", salida)
        self.assertNotIn("\u2029", salida)

    def test_sigue_siendo_json_valido(self):
        import json

        salida = _json_seguro({"hora": "09:00", "activo": True, "n": 3})
        self.assertEqual(json.loads(salida), {"hora": "09:00", "activo": True, "n": 3})

    def test_los_horarios_del_formulario_de_reserva_usan_el_json_seguro(self):
        self.client.session["logueado"] = {"id": None, "nombre": "x", "rol": "Cliente"}
        self.client.session.save()
        r = self.client.get(reverse("sena:usuario_reservar_cita"))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"</script><script>", r.content)
