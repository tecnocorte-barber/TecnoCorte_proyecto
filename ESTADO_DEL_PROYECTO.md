# TecnoCorte — Documentación completa del estado del proyecto

> **Nota de mantenimiento:** este documento es una fotografía del proyecto y
> puede quedar desactualizado después de nuevas funcionalidades. La guía
> operativa vigente está en `DOCUMENTACION_PROYECTO.md`. Actualmente existen
> además recordatorios por correo (`enviar_recordatorios`) y gestión de pedidos
> desde `/admin/pedidos/`.

> Documento descriptivo y exhaustivo del estado actual del proyecto **TecnoCorte**, generado el **15 de octubre de 2026** a partir del análisis directo del código fuente (commit `1834b59`, rama `main`, árbol limpio).

---

## Tabla de contenidos

1. [Identificación del proyecto](#1-identificación-del-proyecto)
2. [Stack tecnológico y dependencias](#2-stack-tecnológico-y-dependencias)
3. [Estructura de archivos](#3-estructura-de-archivos)
4. [Configuración del proyecto](#4-configuración-del-proyecto)
5. [Modelo de datos completo](#5-modelo-de-datos-completo)
6. [Catálogo de servicios](#6-catálogo-de-servicios)
7. [Funciones auxiliares (helpers)](#7-funciones-auxiliares-helpers)
8. [Autenticación y control de acceso](#8-autenticación-y-control-de-acceso)
9. [Mapa completo de URLs](#9-mapa-completo-de-urls)
10. [Descripción funcional de todas las vistas](#10-descripción-funcional-de-todas-las-vistas)
11. [Sistema de notificaciones y correos electrónicos](#11-sistema-de-notificaciones-y-correos-electrónicos)
12. [API REST](#12-api-rest)
13. [Panel de administración de Django](#13-panel-de-administración-de-django)
14. [Frontend: plantillas, includes y estáticos](#14-frontend-plantillas-includes-y-estáticos)
15. [Base de datos y migraciones](#15-base-de-datos-y-migraciones)
16. [Tests (pruebas automatizadas)](#16-tests-pruebas-automatizadas)
17. [Historial de Git](#17-historial-de-git)
18. [Optimizaciones de rendimiento](#18-optimizaciones-de-rendimiento)
19. [Seguridad implementada](#19-seguridad-implementada)
20. [Observaciones y mejoras sugeridas](#20-observaciones-y-mejoras-sugeridas)
21. [Cómo ejecutar el proyecto](#21-cómo-ejecutar-el-proyecto)

---

## 1. Identificación del proyecto

| Dato | Valor |
|---|---|
| Nombre | **TecnoCorte** |
| Tipo | Aplicación web (plataforma de gestión de barberías/peluquerías) |
| Repositorio | https://github.com/tecnocorte-barber/TecnoCorte_proyecto.git |
| Rama activa | `main` (también existe `remotes/origin/main`) |
| Estado del árbol de trabajo | **Limpio** — sin archivos modificados ni sin seguimiento |
| Último commit | `1834b59` — *"Agregar settings_local con SQLite para desarrollo local"* |
| App Django | Una sola app: **`sena`** (proyecto `tecnocorte`) |
| Idioma/ zona horaria | Español de Colombia (`es-co`), `America/Bogota` |

**Qué resuelve:** permitir a los clientes reservar citas en barberías (con calendario de disponibilidad real), comprar productos de una tienda con carrito, y dar a barberos y administradores herramientas para gestionar citas, sedes, horarios, usuarios, productos y notificaciones, todo con roles y una API REST opcional.

---

## 2. Stack tecnológico y dependencias

| Capa | Tecnología | Versión |
|---|---|---|
| Lenguaje | Python (entorno virtual `.venv` en la raíz) | 3.13 (según los `.pyc` compilados) |
| Framework web | Django | 6.1 |
| API REST | Django REST Framework | 3.18.0 |
| Documentación API | drf-spectacular (OpenAPI/Swagger/Redoc) | 0.30.0 |
| Imágenes | Pillow (subida de fotos) | sin fijar (`Pillow`) |
| BD producción | PostgreSQL vía `psycopg` (Supabase/Supavisor, SSL) | psycopg[binary] 3.3.5 |
| BD desarrollo local | SQLite (`db_temporal.sqlite3`) | — |
| Frontend | HTML + CSS + JavaScript **embebidos en las plantillas** | sin framework ni Node |
| Tipografías | Google Fonts (CDN, con `preconnect`) | — |

**Archivo `requirements.txt` (5 líneas):**
```
Django==6.1
djangorestframework==3.18.0
drf-spectacular==0.30.0
Pillow
psycopg[binary]==3.3.5
```

**Sin dependencias de Node:** el commit `4953718` ("eliminar dependencias de node") eliminó `node_modules` y paquetes JS; actualmente no hay `package.json`, ni archivos `.css`/`.js` propios: todo el estilo vive en bloques `<style>` dentro de cada plantilla (~10.100 líneas HTML en total).

---

## 3. Estructura de archivos

```
TecnoCorte_proyecto/
├── manage.py                       # Script de gestión de Django
├── requirements.txt                # Dependencias (5)
├── .env                            # Variables de entorno (NO versionado; 14 claves)
├── .gitignore                      # Ignora .env, *.sqlite3, __pycache__, .idea, etc.
├── db_temporal.sqlite3             # BD SQLite local (282 KB; ignorada por Git)
├── .pytest_cache/                  # Caché de pytest
├── .venv/                          # Entorno virtual de Python
├── media/                          # Archivos subidos por los usuarios
│   ├── galeria/                    # Fotos de galerías de peluquerías (vacío)
│   ├── peluquerias/                # Imágenes de sedes (vacío)
│   ├── productos/                  # Fotos de productos (subidas por el Admin)
│   └── fotos_perfil/               # Fotos de perfil de usuarios
├── tecnocorte/                     # Paquete de configuración del proyecto
│   ├── settings.py                 # Configuración principal (PostgreSQL + .env)
│   ├── settings_local.py           # Configuración de desarrollo (SQLite)
│   ├── urls.py                     # Rutas raíz (app, admin, API docs)
│   ├── wsgi.py                     # Punto de entrada WSGI
│   └── __init__.py
└── sena/                           # ÚNICA app del proyecto
    ├── models.py                   # 13 modelos (incluye Configuracion)
    ├── views.py                    # ~85 vistas + helpers
    ├── urls.py                     # ~85 rutas
    ├── api.py                      # 4 ViewSets DRF (86 líneas)
    ├── serializers.py              # 4 serializers (95 líneas)
    ├── admin.py                    # 13 modelos en el admin
    ├── utilidades.py               # Decorador de autorización + validador de contraseña (45 líneas)
    ├── middleware.py               # MantenimientoMiddleware (modo mantenimiento)
    ├── context_processors.py       # 4 procesadores de contexto
    ├── apps.py                     # SenaConfig (AutoField)
    ├── tests.py                    # Suite de tests
    ├── tests_fotos.py              # Tests de fotos, moderación y configuración
    ├── migrations/                 # 25 archivos de migración (todas aplicadas)
    ├── templates/                  # Plantillas HTML
    │   ├── base/base.html          # Plantilla base
    │   ├── includes/               # Fragmentos reutilizables
    │   ├── publicos/               # Plantillas públicas (incluye mantenimiento.html)
    │   ├── carrito/                # Plantillas de tienda/compra
    │   ├── usuarios/               # Plantillas del cliente
    │   ├── peluqueros/             # Plantillas del barbero
    │   ├── administrador/          # Plantillas del admin (incluye admin_galeria.html y admin_configuracion.html)
    │   └── emails/notificacion.html # Plantilla de correos
    └── static/sena/images/         # 12 imágenes estáticas (logo y fotos de barbería)
```

**Archivos estáticos (`sena/static/sena/images/`):** `Logo.png`, `Tijeras.jpeg`, `aceite_barba.jpeg`, `arreglo_barba.jpeg`, `barberia_centro.jpg`, `barberia_itagui.jpeg`, `cepillo.jpeg`, `corte_cabello.jpeg`, `corte_masculino.jpg`, `maquina_motilar.jpg`, `pomada_barba.jpeg`, `servicio_completo.jpeg`. **No hay** archivos CSS ni JS estáticos propios.

---

## 4. Configuración del proyecto

### 4.1 `tecnocorte/settings.py` (142 líneas)

- **Carga de variables de entorno:** lee el archivo `.env` línea por línea y hace `os.environ.setdefault` de cada `CLAVE=valor` (sin añadir dependencias como `python-dotenv`).
- **Variables principales:**
  - `DJANGO_SECRET_KEY` (con valor por defecto local si no existe).
  - `DJANGO_DEBUG` (`True` por defecto).
  - `DJANGO_ALLOWED_HOSTS` (por defecto `localhost,127.0.0.1`, separados por comas).
- **`INSTALLED_APPS`:** apps estándar de Django + `rest_framework`, `rest_framework.authtoken`, `sena`, `drf_spectacular`.
- **`MIDDLEWARE`:** los 7 middleware estándar (security, sessions, common, csrf, auth, messages, clickjacking) más `sena.middleware.MantenimientoMiddleware` al final, que aplica el **modo mantenimiento** (solo el Admin navega; el resto ve `publicos/mantenimiento.html` con HTTP 503; login, logout, `/admin/`, estáticos y media quedan siempre accesibles).
- **`TEMPLATES`:** `DIRS` apunta a `sena/templates`; registra 4 **context processors propios**: `carrito_contexto`, `notificaciones_contexto`, `formulario_contexto`, `configuracion_contexto`.
- **Base de datos (producción):** PostgreSQL con:
  - `CONN_MAX_AGE` (reutilización de conexiones, por defecto 60 s).
  - `sslmode: require` y `prepare_threshold: None` (compatibilidad con el pooler transaccional de Supavisor, que no soporta consultas preparadas).
  - Credenciales desde `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (por defecto puerto `6543`).
- **Localización:** `LANGUAGE_CODE='es-co'`, `TIME_ZONE='America/Bogota'`, `USE_TZ=True`.
- **Archivos:** `STATIC_URL='/static/'`, `STATIC_ROOT=staticfiles/`, `STATICFILES_DIRS=sena/static`, `MEDIA_URL='/media/'`, `MEDIA_ROOT=media/`.
- **Correo:** en `DEBUG` usa el backend de **consola**; en producción usa **SMTP** con `EMAIL_HOST`, `EMAIL_PORT` (587), `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`. `CONTACT_EMAIL` por defecto `tecnocorte083@gmail.com`.
- **Seguridad web:** `SESSION_COOKIE_SECURE` y `CSRF_COOKIE_SECURE` activos cuando `DEBUG=False`; `SECURE_SSL_REDIRECT` y `SECURE_HSTS_SECONDS` configurables por variable de entorno.
- **REST_FRAMEWORK:** permiso por defecto `IsAuthenticated`; throttling `AnonRateThrottle` (100/día) y `UserRateThrottle` (1000/día); esquema OpenAPI con `drf_spectacular`.
- **SPECTACULAR_SETTINGS:** título *"Mi API"*, descripción *"Documentación de la API"*, versión `1.0.0` (textos genéricos, sin personalizar).

### 4.2 `tecnocorte/settings_local.py` (7 líneas)

Extiende `settings.py` con `from .settings import *` y **reemplaza `DATABASES`** por SQLite apuntando a `db_temporal.sqlite3`. Permite desarrollar sin PostgreSQL. Se usa con `DJANGO_SETTINGS_MODULE=tecnocorte.settings_local`.

### 4.3 `tecnocorte/urls.py` (17 líneas)

| Ruta | Destino |
|---|---|
| `''` | `include('sena.urls')` (toda la app) |
| `api/auth/` | `include('rest_framework.urls')` (login de API de DRF) |
| `admin/` | Panel de administración de Django |
| `api/schema/` | Esquema OpenAPI (drf-spectacular) |
| `api/docs/` | Swagger UI |
| `api/redoc/` | Redoc |
| + `static(...)` | Sirve `media/` en desarrollo |

### 4.4 `.env` (14 claves, no versionado)

Claves presentes: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`.

### 4.5 `.gitignore`

Ignora: `__pycache__/`, `*.pyc`, `node_modules/`, `*.sqlite3`, `venv/`, `.env`, `.DS_Store`, `DOCUMENTACION_PROYECTO.md`, `.idea/`.

---

## 5. Modelo de datos completo

Archivo `sena/models.py` — **12 modelos**, 219 líneas. Todos usan `AutoField` como clave primaria por defecto.

### 5.1 `Usuario`
Cuenta del sistema con autenticación propia (no usa `django.contrib.auth`).

| Campo | Tipo | Detalles |
|---|---|---|
| `nombre` | CharField(100) | Nombre |
| `apellido` | CharField(100) | Apellido |
| `email` | EmailField | **Único** (clave de login) |
| `password` | CharField(128) | Hash (make_password) |
| `telefono` | CharField(20) | Opcional (`blank=True`) |
| `rol` | CharField(15) | Choices: `Admin`, `Barbero`, `Cliente` (default `Cliente`) |
| `peluqueria` | FK → Peluqueria | `SET_NULL`, nullable; obligatoria para barberos (relación `usuarios`) |
| `foto` | ImageField | `upload_to="fotos_perfil/"`, opcional |
| `activo` | BooleanField | default `True` (bandera de suspensión) |
| `fecha_creacion` | DateTimeField | `auto_now_add=True` |

`__str__`: `"{nombre} - {rol}"`.

### 5.2 `Peluqueria`
Sede o barbería.

| Campo | Tipo | Detalles |
|---|---|---|
| `nombre` | CharField(100) | — |
| `ubicacion` | CharField(200) | Dirección |
| `telefono` | CharField(20) | — |
| `dueno` | FK → Usuario | `SET_NULL`, nullable, related_name `peluquerias_dueno` (el barbero dueño) |
| `descripcion` | TextField | `blank=True`, default `""` |
| `imagen` | ImageField | `upload_to="peluquerias/"`, opcional |

### 5.3 `ImagenPeluqueria`
Galería de fotos por peluquería.

| Campo | Tipo | Detalles |
|---|---|---|
| `peluqueria` | FK → Peluqueria | `CASCADE`, related_name `galeria` |
| `imagen` | ImageField | `upload_to="galeria/"` |
| `descripcion` | CharField(200) | Opcional |
| `fecha` | DateTimeField | `auto_now_add=True` |

`Meta`: `ordering = ["-fecha"]`. Límite de 5 fotos por galería, impuesto en la vista (`peluquero_agregar_imagen`).

### 5.4 `Producto`
Artículo de la tienda.

| Campo | Tipo | Detalles |
|---|---|---|
| `nombre` | CharField(100) | — |
| `descripcion` | TextField | `blank=True` |
| `precio` | **IntegerField** | Precio en COP (entero, sin decimales) |
| `imagen` | **ImageField** | `upload_to="productos/"`, `blank=True`, `max_length=500`. La sube el Admin desde el panel; el archivo se guarda en `MEDIA_ROOT/productos/` y la referencia en la BD |
| `categoria` | CharField(20) | Choices: `Herramientas`, `Fijacion` (Fijación & Textura), `Cuidado` (Cuidado Capilar), `Barba` (Barba & Afeitado) |
| `stock` | IntegerField | default 0 |
| `disponible` | BooleanField | default True |
| `fecha_creacion` | DateTimeField | `auto_now_add=True` |

### 5.5 `Reserva`
Cita de un cliente con un barbero.

| Campo | Tipo | Detalles |
|---|---|---|
| `cliente` | FK → Usuario | `PROTECT`, related_name `reservas_cliente` |
| `peluquero` | FK → Usuario | `PROTECT`, related_name `reservas_peluquero` |
| `peluqueria` | FK → Peluqueria | `PROTECT` |
| `fecha` | DateField | — |
| `hora` | TimeField | — |
| `servicio` | CharField(100) | `blank=True`, default `"Corte de Cabello"` (nombre del catálogo `SERVICIOS`) |
| `estado` | CharField(20) | Choices: `Pendiente`, `Confirmada`, `Completada`, `Cancelada` (default `Pendiente`) |
| `recordatorio_correo_enviado` | DateTimeField | Marca el recordatorio automático ya enviado para evitar duplicados |

### 5.6 `Pedido`
Compra de productos.

| Campo | Tipo | Detalles |
|---|---|---|
| `cliente` | FK → Usuario | `PROTECT`, related_name `pedidos` |
| `fecha` | DateTimeField | `auto_now_add=True` |
| `total` | IntegerField | default 0 (COP) |
| `estado` | CharField(20) | Choices: `Pendiente`, `Listo para recoger`, `Entregado`, `Cancelado` |
| `pago_confirmado` | BooleanField | El administrador confirma el pago realizado en la tienda |
| `fecha_pago` | DateTimeField | Momento en que el Admin confirmó el pago |
| `fecha_entrega` | DateTimeField | Momento en que el pedido fue entregado |

### 5.7 `PedidoProducto`
Detalle línea a línea de cada pedido.

| Campo | Tipo | Detalles |
|---|---|---|
| `pedido` | FK → Pedido | `CASCADE`, related_name `productos` |
| `producto` | FK → Producto | `PROTECT`, related_name `pedidos_productos` |
| `cantidad` | IntegerField | default 1 |
| `precio` | IntegerField | default 0 (precio al momento de la compra) |

### 5.8 `RegistroIngreso`
Historial de inicios de sesión.

| Campo | Tipo | Detalles |
|---|---|---|
| `usuario` | FK → Usuario | `CASCADE`, related_name `ingresos` |
| `rol` | CharField(15) | Rol con el que se ingresó |
| `fecha` | DateTimeField | `auto_now_add=True` |
| `ip` | CharField(45) | `REMOTE_ADDR` (soporta IPv6) |

### 5.9 `Notificacion`
Aviso interno a un usuario.

| Campo | Tipo | Detalles |
|---|---|---|
| `usuario` | FK → Usuario | `CASCADE`, related_name `notificaciones` |
| `reserva` | FK → Reserva | `CASCADE`, nullable, related_name `notificaciones` |
| `mensaje` | CharField(255) | Texto del aviso |
| `leida` | BooleanField | default False |
| `fecha` | DateTimeField | `auto_now_add=True` |

### 5.10 `HorarioTrabajo`
Horario semanal por peluquería.

| Campo | Tipo | Detalles |
|---|---|---|
| `peluqueria` | FK → Peluqueria | `CASCADE`, related_name `horarios`, default=1 |
| `dia_semana` | PositiveSmallIntegerField | Choices 0–6: Lunes…Domingo |
| `activo` | BooleanField | default True |
| `hora_inicio` | TimeField | default `09:00` |
| `hora_fin` | TimeField | default `18:00` |

`Meta`: `unique_together = ("peluqueria", "dia_semana")`, `ordering = ["dia_semana"]`.

### 5.11 `BloqueoHorario`
Día u hora bloqueada para no recibir citas.

| Campo | Tipo | Detalles |
|---|---|---|
| `peluqueria` | FK → Peluqueria | `CASCADE`, related_name `bloqueos`, default=1 |
| `fecha` | DateField | — |
| `hora` | TimeField | **nullable**: si es `None`, bloquea todo el día |
| `motivo` | CharField(150) | Opcional |

`Meta`: `ordering = ["fecha", "hora"]`.

### 5.12 `MensajeContacto`
Mensajes del formulario de ayuda.

| Campo | Tipo | Detalles |
|---|---|---|
| `nombre` | CharField(100) | — |
| `email` | EmailField | — |
| `asunto` | CharField(150) | — |
| `mensaje` | TextField | — |
| `fecha` | DateTimeField | `auto_now_add=True` |
| `leido` | BooleanField | default False |

`Meta`: `ordering = ["-fecha"]`.

### 5.13 `Calificacion`
Puntuación del cliente al barbero (una por reserva, `OneToOne`).

| Campo | Tipo | Detalles |
|---|---|---|
| `reserva` | **OneToOne** → Reserva | `CASCADE`, related_name `calificacion` |
| `cliente` | FK → Usuario | `CASCADE`, related_name `calificaciones_hechas` |
| `barbero` | FK → Usuario | `CASCADE`, related_name `calificaciones_recibidas` |
| `puntuacion` | PositiveSmallIntegerField | 1–5 (validado en la vista) |
| `comentario` | TextField | `blank=True` |
| `fecha` | DateTimeField | `auto_now_add=True` |

`Meta`: `ordering = ["-fecha"]`.

### 5.14 `Configuracion`
Configuración general del sitio (registro único, `pk=1`). La administra el Admin desde `/admin/configuracion/`.

| Campo | Tipo | Detalles |
|---|---|---|
| `sitio_nombre` | CharField(100) | default `"TecnoCorte"` |
| `correo_contacto` | EmailField | default `tecnocorte083@gmail.com` |
| `texto_aviso` | CharField(200) | `blank=True` |
| `registro_abierto` | BooleanField | default True — permite crear cuentas de cliente |
| `mostrar_telefonos` | BooleanField | default True — teléfonos de barberías al público |
| `mostrar_ubicaciones` | BooleanField | default True — ubicaciones al público |
| `mostrar_galeria` | BooleanField | default True — galería de fotos al público |
| `mostrar_calificaciones` | BooleanField | default True — reseñas en los paneles de barbero |
| `modo_mantenimiento` | BooleanField | default False — solo el Admin navega el sitio |
| `mensaje_mantenimiento` | CharField(200) | `blank=True` |
| `actualizado` | DateTimeField | `auto_now=True` |

Métodos: `save()` fuerza `pk=1` y limpia la caché `configuracion_sitio`; `cargar()` devuelve la fila (creándola si no existe) con caché de 300 s.

---

## 6. Catálogo de servicios

Definido como constante `SERVICIOS` en `views.py` (no está en la base de datos):

| Servicio | Descripción | Duración | Minutos | Precio (COP) |
|---|---|---|---|---|
| **Corte de Cabello** | Lavado, corte preciso con tijera y máquina, peinado con productos premium. | 45 Minutos | 45 | $40.000 |
| **Arreglo de Barba** | Toalla caliente, perfilado exacto, hidratación con aceites esenciales. | 30 Minutos | 30 | $30.000 |
| **Combo Completo** | Corte de cabello + arreglo de barba + limpieza facial. | 1 Hora 15 Min | 75 | $60.000 |

La duración se usa para bloquear el tiempo del barbero y para validar que la cita quepa dentro del horario de atención. Un servicio desconocido usa **30 minutos por defecto** (`minutos_servicio`).

---

## 7. Funciones auxiliares (helpers)

### 7.1 En `sena/utilidades.py`

- **`validar_password(password)`** → devuelve `""` si la contraseña es válida, o el mensaje de error. Reglas: mínimo 8 caracteres, al menos una mayúscula, un número y un símbolo.
- **`autorizacion(roles=[])`** → decorador de vistas. Pasos:
  1. Si no hay `request.session["logueado"]`, redirige a `sena:login?next=<ruta>`.
  2. Verifica que el usuario de la sesión **exista y esté activo** en la BD; si no, borra la sesión y redirige al login.
  3. Si se pasaron `roles`, comprueba que el rol de la sesión esté permitido; si no, redirige al login.

### 7.2 En `sena/context_processors.py`

- **`carrito_visible(request)`** → `False` si el carrito de la sesión pertenece a otra cuenta (evita que un usuario vea el carrito de otro).
- **`guardar_carrito_activo(request)`** → guarda el carrito activo en `session["carritos_usuario"]` bajo la clave del usuario id o `"anonimo"`.
- **`cargar_carrito_usuario(request, usuario_id)`** → cambia el carrito activo al de una cuenta; si la cuenta es nueva y hay carrito anónimo, lo hereda.
- **`carrito_contexto(request)`** → expone `{"cantidad": n}` (unidades totales del carrito) en todas las plantillas.
- **`notificaciones_contexto(request)`** → expone `notificaciones_no_leidas` y `mensajes_no_leidos` (solo para Admin); los contadores se cachean **20 segundos** para no consultar la BD remota en cada página.
- **`formulario_contexto(request)`** → en POST, serializa `request.POST` (sin campos de contraseña) en `form_post` para repoblar formularios.
- **`configuracion_contexto(request)`** → expone `config` (la fila `Configuracion`) en todas las plantillas para respetar la privacidad (teléfonos, ubicaciones, galería) y el aviso del sitio.

### 7.3 En `sena/views.py` (helpers)

- **`_horarios_para_template(peluqueria_id=None)`** → convierte `HorarioTrabajo` y `BloqueoHorario` a JSON (`horarios_json`, `bloqueos_json`) más `fecha_hoy` y `hora_actual` para el calendario JavaScript.
- **`_reservas_para_template()`** → lista de reservas **no canceladas** como JSON (`barbero`, `fecha`, `hora`, `minutos`) para que el calendario ocupe los horarios ocupados.
- **`_id_entero(valor)`** → convierte un valor a `int` solo si son dígitos puros; devuelve `None` si no (previene inyección de IDs).
- **`contexto_carrito(request)`** → construye el contexto del carrito: `items` (producto, cantidad, subtotal), `total`, `cantidad`, más los mensajes flash de sesión `mensaje_tienda` y `mensaje_carrito` (se consumen al leerlos con `pop`).
- **`registrar_ingreso(request, usuario)`** → crea un `RegistroIngreso` con IP (`REMOTE_ADDR`) en cada login.
- **`cita_disponible(fecha_texto, hora_texto, peluqueria_id=None, servicio=None)`** → devuelve `(bool, mensaje)`. Valida en orden: formato de fecha/hora; no fecha pasada; no hora pasada si es hoy; que exista `HorarioTrabajo` para ese día de la semana (y esté activo); que la cita (con su duración) quepa dentro del horario; que el día no esté bloqueado por completo; que no choque con un bloqueo por hora (con margen de 30 minutos).
- **`minutos_servicio(servicio)`** → duración del servicio según `SERVICIOS` (30 por defecto).
- **`formato_cita(reserva)`** → texto legible `"dd/mm/AAAA a las HH:MM"` para notificaciones y correos.
- **`enviar_correo(usuario, asunto, cuerpo, ...)`** / **`enviar_correo_destino(destinatario, ...)`** → envían correo HTML (versión texto + alternativa HTML) usando la plantilla `emails/notificacion.html`, con el **logo embebido** vía `Content-ID <tecnocorte-logo>`; `fail_silently=True` (un fallo de SMTP nunca rompe la operación).
- **`enviar_correo_cita(...)`** → envoltorio de `enviar_correo` con botón "Revisar mi cita".
- **`token_recuperacion(usuario)`** → token firmado (`signing.dumps` con sal `tecnocorte-password-reset`, compresión activa) que incluye el id y una "versión" `salted_hmac` de la contraseña actual.
- **`usuario_desde_token(token)`** → valida el token (máx. **1 hora**, `max_age=3600`), comprueba firma, que el usuario exista y esté activo, y que la versión del token coincida con la contraseña actual usando **`hmac.compare_digest`** (comparación constante; invalida el token al cambiar la contraseña).
- **`notificar_suspension_barbero(request, barbero)`** → al suspender un barbero, pone sus citas futuras (no pasadas, no canceladas/completadas) en estado `Pendiente` y notifica + envía correo a cada cliente con el enlace para reagendar.
- **`barbero_esta_disponible(barbero_id, fecha, hora, servicio, reserva_actual=None)`** → `(bool, mensaje)`; comprueba que el barbero no tenga otra cita que se cruce con la ventana propuesta (considerando la duración del servicio); puede excluir la reserva que se está editando.
- **`_cliente_o_invitado(request)`** → `True` si no hay login o el rol es `Cliente` (barberos y admins no pueden comprar).
- **`_peluqueria_del_barbero(usuario_id)`** → devuelve la peluquería del barbero: primero la que es **dueño** (`Peluqueria.dueno`), luego la que el Admin le **asignó** (`Usuario.peluqueria`) y, en último caso, la hereda de la primera reserva. El barbero **ya no crea** su propia peluquería: la crea o asigna el Admin.
- **`_motivo_eliminacion(request)`** → devuelve el texto (recortado) del campo `motivo` del POST, o `None` si viene vacío. Lo usan las vistas de borrado de fotos: **sin motivo no se borra nada**.
- **`avisar_foto_eliminada(usuario, descripcion_foto, motivo, request=None)`** → envía un correo a quien subió la foto explicando **por qué** se eliminó (usando `enviar_correo`).
- **`notificar_producto_agotado(producto)`** → notifica a todos los admins activos cuando un producto llega a stock 0.
- **`_borrar_archivo(campo)`** → borra el archivo de un `ImageField` sin tocar el registro; tolera errores (por ejemplo, valores antiguos que eran URLs).
- **`datos_producto(request, producto)`** → aplica el POST al modelo `Producto`: precio y stock se enteran y nunca quedan negativos; `disponible` solo es `True` si el checkbox está activo **y** `stock > 0`; gestiona la **foto** (si llega `imagen` la reemplaza, si llega `quitar_imagen` la borra); si el stock pasa de >0 a 0, notifica el agotamiento.

---

## 8. Autenticación y control de acceso

- **No se usa `django.contrib.auth`**: el login es propio contra el modelo `Usuario`.
- **Sesión:** `request.session["logueado"] = {"id", "nombre", "rol"}`. El login verifica `check_password` contra el hash, que la cuenta esté `activo`, y registra el ingreso.
- **Redirección por rol tras login/`/`:**
  - `Admin` → `sena:admin_reservas`
  - `Barbero` → `sena:peluquero_dashboard`
  - `Cliente` → `sena:inicio` (landing con carrito)
- **Protección de vistas:** el decorador `@autorizacion([...])` (ver §7.1) en **todas** las vistas privadas; verifica sesión + cuenta activa + rol.
- **Recuperación de contraseña:** token firmado de 1 hora atado a la contraseña actual (ver §7.3).
- **Cambio de contraseña:** vista propia (`cambiar_password`) que exige la contraseña actual y aplica `validar_password`.
- **Registro:** solo crea clientes (`rol="Cliente"`), con validación de email único y contraseña segura; inicia sesión automáticamente.
- **Alta de barberos:** solo el Admin crea/edita barberos y **debe asignarles una peluquería** (`Usuario.peluqueria`), que es obligatoria. El barbero **no** se registra solo ni crea su propia peluquería; si aún no tiene una asignada, su panel se lo indica con un aviso (`SIN_PELUQUERIA`).
- **Carrito por usuario:** los carritos se guardan por cuenta en la sesión (`carritos_usuario`), evitando fugas entre cuentas (ver §7.2).

---

## 9. Mapa completo de URLs

Todas las rutas están en `sena/urls.py` con `app_name = "sena"`. API de DRF montada con `DefaultRouter`.

### 9.1 Públicas (sin login)

| URL | Vista | Nombre | Método |
|---|---|---|---|
| `/` | `inicio` | `inicio` | GET |
| `/login/` | `login` | `login` | GET/POST |
| `/recuperar-password/` | `solicitar_recuperacion` | `solicitar_recuperacion` | GET/POST |
| `/restablecer-password/<token>/` | `restablecer_password` | `restablecer_password` | GET/POST |
| `/registro/` | `registro` | `registro` | GET/POST |
| `/logout/` | `logout` | `logout` | GET |
| `/como_funciona/` | `como_funciona` | `como_funciona` | GET |
| `/sobre_nosotros/` | `sobre_nosotros` | `sobre_nosotros` | GET |
| `/ayuda/` | `ayuda` | `ayuda` | GET/POST |

### 9.2 Carrito (funciona sin login)

| URL | Vista | Nombre | Método |
|---|---|---|---|
| `/carrito/` | `carrito` | `carrito` | GET |
| `/carrito/agregar/<producto_id>/` | `agregar_carrito` | `agregar_carrito` | GET/POST (AJAX aceptado) |
| `/carrito/actualizar/<producto_id>/` | `actualizar_carrito` | `actualizar_carrito` | POST |
| `/carrito/eliminar/<producto_id>/` | `eliminar_carrito` | `eliminar_carrito` | GET/POST |
| `/carrito/finalizar/` | `finalizar_pedido` | `finalizar_pedido` | GET/POST — **solo Cliente** |
| `/carrito/pedido_exitoso/<pedido_id>/` | `pedido_exitoso` | `pedido_exitoso` | GET — **solo Cliente** |

### 9.3 Panel del Cliente (rol `Cliente`)

| URL | Vista | Nombre |
|---|---|---|
| `/usuario/dashboard/` | `usuario_dashboard` | `usuario_dashboard` |
| `/usuario/tienda/` | `usuario_tienda` | `usuario_tienda` |
| `/usuario/servicios/` | `usuario_servicios` | `usuario_servicios` |
| `/usuario/peluquerias/` | `usuario_peluquerias` | `usuario_peluquerias` |
| `/usuario/peluquerias/<id>/` | `usuario_peluqueria_detalle` | `usuario_peluqueria_detalle` |
| `/usuario/reservar_cita/` | `usuario_reservar_cita` | `usuario_reservar_cita` |
| `/usuario/pre_confirmar/` | `usuario_pre_confirmar` | `usuario_pre_confirmar` |
| `/usuario/confirmar_reserva/` | `usuario_confirmar_reserva` | `usuario_confirmar_reserva` |
| `/usuario/perfil/` | `usuario_perfil` | `usuario_perfil` |
| `/usuario/cita/<reserva_id>/cancelar/` | `usuario_cancelar_reserva` | `usuario_cancelar_reserva` |
| `/usuario/cita/<reserva_id>/editar/` | `usuario_editar_reserva` | `usuario_editar_reserva` |
| `/usuario/cita/<reserva_id>/calificar/` | `usuario_calificar` | `usuario_calificar` |
| `/usuario/notificaciones/` | `usuario_notificaciones` | `usuario_notificaciones` |
| `/usuario/notificaciones/leidas/` | `usuario_marcar_notificaciones_leidas` | `usuario_marcar_notificaciones_leidas` |
| `/usuario/cita/<reserva_id>/confirmar_peluquero/` | `usuario_confirmar_cita_peluquero` | `usuario_confirmar_cita_peluquero` |
| `/cuenta/cambiar-password/` | `cambiar_password` | `cambiar_password` (Cliente o Barbero) |

### 9.4 Panel del Barbero (rol `Barbero`)

| URL | Vista | Nombre |
|---|---|---|
| `/peluquero/dashboard/` | `peluquero_dashboard` | `peluquero_dashboard` |
| `/peluquero/perfil/` | `peluquero_perfil` | `peluquero_perfil` |
| `/peluquero/crear_cita/` | `peluquero_crear_cita` | `peluquero_crear_cita` |
| `/peluquero/cita/<cita_id>/estado/` | `peluquero_cambiar_estado` | `peluquero_cambiar_estado` |
| `/peluquero/notificaciones/` | `peluquero_notificaciones` | `peluquero_notificaciones` |
| `/peluquero/peluqueria/editar/` | `peluquero_editar_peluqueria` | `peluquero_editar_peluqueria` |
| `/peluquero/galeria/` | `peluquero_galeria` | `peluquero_galeria` |
| `/peluquero/galeria/agregar/` | `peluquero_agregar_imagen` | `peluquero_agregar_imagen` |
| `/peluquero/galeria/<imagen_id>/eliminar/` | `peluquero_eliminar_imagen` | `peluquero_eliminar_imagen` |

### 9.5 Panel del Administrador (rol `Admin`)

| URL | Vista | Nombre |
|---|---|---|
| `/admin/dashboard/` | `admin_dashboard` | `admin_dashboard` |
| `/admin/usuarios/` | `admin_usuarios` | `admin_usuarios` |
| `/admin/crear_usuario/` | `admin_crear_usuario` | `admin_crear_usuario` |
| `/admin/editar_usuario/<id>/` | `admin_editar_usuario` | `admin_editar_usuario` |
| `/admin/eliminar_usuario/<id>/` | `admin_eliminar_usuario` | `admin_eliminar_usuario` |
| `/admin/suspender_usuario/<id>/` | `admin_suspender_usuario` | `admin_suspender_usuario` |
| `/admin/peluqueros/` | `admin_peluqueros` | `admin_peluqueros` |
| `/admin/crear_peluquero/` | `admin_crear_peluquero` | `admin_crear_peluquero` |
| `/admin/editar_peluquero/<id>/` | `admin_editar_peluquero` | `admin_editar_peluquero` |
| `/admin/eliminar_peluquero/<id>/` | `admin_eliminar_peluquero` | `admin_eliminar_peluquero` |
| `/admin/reservas/` | `admin_reservas` | `admin_reservas` |
| `/admin/crear_reserva/` | `admin_crear_reserva` | `admin_crear_reserva` |
| `/admin/editar_reserva/<id>/` | `admin_editar_reserva` | `admin_editar_reserva` |
| `/admin/eliminar_reserva/<id>/` | `admin_eliminar_reserva` | `admin_eliminar_reserva` |
| `/admin/cancelar_reserva/<id>/` | `admin_cancelar_reserva` | `admin_cancelar_reserva` |
| `/admin/ingresos/` | `admin_ingresos` | `admin_ingresos` |
| `/admin/perfil/` | `admin_perfil` | `admin_perfil` |
| `/admin/horarios/` | `admin_horarios` | `admin_horarios` |
| `/admin/eliminar_bloqueo/<id>/` | `admin_eliminar_bloqueo` | `admin_eliminar_bloqueo` |
| `/admin/peluquerias/` | `admin_peluquerias` | `admin_peluquerias` |
| `/admin/peluquerias/nueva/` | `admin_crear_peluqueria` | `admin_crear_peluqueria` |
| `/admin/peluquerias/<id>/editar/` | `admin_editar_peluqueria` | `admin_editar_peluqueria` |
| `/admin/peluquerias/<id>/eliminar/` | `admin_eliminar_peluqueria` | `admin_eliminar_peluqueria` |
| `/admin/productos/` | `admin_productos` | `admin_productos` |
| `/admin/productos/nuevo/` | `admin_crear_producto` | `admin_crear_producto` |
| `/admin/productos/<id>/editar/` | `admin_editar_producto` | `admin_editar_producto` |
| `/admin/productos/<id>/eliminar/` | `admin_eliminar_producto` | `admin_eliminar_producto` |
| `/admin/productos/<id>/quitar_imagen/` | `admin_quitar_imagen_producto` | `admin_quitar_imagen_producto` |
| `/admin/galeria/` | `admin_galeria` | `admin_galeria` |
| `/admin/galeria/<id>/eliminar/` | `admin_eliminar_imagen_galeria` | `admin_eliminar_imagen_galeria` |
| `/admin/peluquerias/<id>/quitar_foto/` | `admin_quitar_foto_peluqueria` | `admin_quitar_foto_peluqueria` |
| `/admin/usuarios/<id>/quitar_foto/` | `admin_quitar_foto_usuario` | `admin_quitar_foto_usuario` |
| `/admin/configuracion/` | `admin_configuracion` | `admin_configuracion` |
| `/admin/mensajes/` | `admin_mensajes` | `admin_mensajes` |
| `/admin/notificaciones/` | `admin_notificaciones` | `admin_notificaciones` |

### 9.6 API REST

| URL | Origen |
|---|---|
| `/api/usuarios/`, `/api/usuarios/<pk>/` | Router DRF → `UsuarioViewSet` |
| `/api/peluquerias/`, `/api/peluquerias/<pk>/` | Router DRF → `PeluqueriaViewSet` |
| `/api/productos/`, `/api/productos/<pk>/` | Router DRF → `ProductoViewSet` |
| `/api/reservas/`, `/api/reservas/<pk>/` | Router DRF → `ReservaViewSet` |
| `/api/auth/` | Login/sesión de DRF |
| `/api/schema/`, `/api/docs/` (Swagger), `/api/redoc/` | Documentación OpenAPI |

---

## 10. Descripción funcional de todas las vistas

`sena/views.py` — **1.955 líneas**, ~80 funciones de vista.

### 10.1 Públicas

- **`inicio`** — Si hay sesión de Admin redirige a `admin_reservas`; de Barbero a `peluquero_dashboard`; en otros casos renderiza `publicos/index.html` con el contexto del carrito.
- **`login`** — POST: aplica **anti fuerza bruta** (caché por correo+IP: 5 intentos fallidos → bloqueo de 5 minutos, con contador visible de intentos restantes). Verifica hash, que la cuenta esté activa, guarda el carrito anónimo y carga el del usuario, registra el ingreso, y redirige según `next` seguro (validado con `url_has_allowed_host_and_scheme`) o según rol.
- **`solicitar_recuperacion`** — Valida el correo (`validate_email`); si el usuario existe y está activo, genera el token y envía el correo con enlace (válido 1 hora). Siempre muestra "enviado" (no filtra qué correos existen).
- **`restablecer_password`** — Valida el token; en POST exige coincidencia de contraseñas y `validar_password`; guarda el hash y redirige al login.
- **`logout`** — Guarda el carrito activo, borra `logueado`, restaura el carrito anónimo y redirige al inicio.
- **`registro`** — Si `registro_abierto` está desactivado en `Configuracion`, muestra el aviso de registro cerrado. Si no: valida campos obligatorios, formato de email, reglas de contraseña y email no duplicado; crea el `Usuario` (rol Cliente), notifica a todos los admins activos, envía correo de bienvenida (HTML con logo), inicia sesión, registra el ingreso y respeta `next`.
- **`como_funciona`** / **`sobre_nosotros`** — Páginas estáticas.
- **`ayuda`** — GET: formulario. POST: crea `MensajeContacto`, notifica a los admins activos y envía correo a `CONTACT_EMAIL` (el asunto se limpia de saltos de línea para evitar inyección de cabeceras).

### 10.2 Carrito y compra

- **`carrito`** — Renderiza el carrito con items, total y cantidad.
- **`agregar_carrito`** — Soporta **AJAX** (`X-Requested-With`) devolviendo JSON, y normal (redirect + mensaje de sesión). Reglas: solo invitados o Clientes; valida que el producto exista, esté disponible y haya stock (tanto total como por cantidad en el carrito); incrementa unidades. Si el carrito no es visible (pertenecía a otra cuenta), lo recarga o limpia.
- **`actualizar_carrito`** — POST; limita la cantidad al stock disponible (con mensaje si lo supera); cantidad ≤ 0 elimina el producto. En AJAX devuelve item, subtotal, total y `empty`.
- **`eliminar_carrito`** — Quita el producto; en AJAX devuelve total/cantidad/`empty`.
- **`finalizar_pedido`** — Solo Cliente y con items. POST: dentro de una **transacción atómica** hace `select_for_update` de los productos, revalida stock, crea el `Pedido` (estado Pendiente) y sus `PedidoProducto`, descuenta stock; si un stock llega a 0 marca `disponible=False` y notifica a los admins del agotamiento. Luego vacía el carrito, crea una notificación al cliente con el resumen (máx. 3 productos nombrados) y redirige a `pedido_exitoso`.
- **`pedido_exitoso`** — Muestra el pedido **solo si pertenece al cliente de la sesión**.

### 10.3 Cliente

- **`usuario_dashboard`** / **`usuario_tienda`** — Ambas renderizan `usuarios/usuario_tienda.html` con todos los `Producto`.
- **`usuario_servicios`** — Lista el catálogo `SERVICIOS`.
- **`usuario_peluquerias`** — Lista todas las `Peluqueria` (si no tienen imagen, el template muestra el logo); respeta la privacidad (oculta ubicación/teléfono según `Configuracion`).
- **`usuario_peluqueria_detalle`** — Detalle de la sede y su galería (`404` si no existe); la galería, ubicación y teléfono se ocultan según `Configuracion`.
- **`usuario_reservar_cita`** — Formulario de reserva: barberos activos, peluquerías, servicios, y **JSON de horarios, bloqueos, reservas ocupadas, fecha de hoy y hora actual** para el calendario JS. Acepta preselección por GET (`servicio`, `peluqueria`), validada contra el catálogo y la BD.
- **`usuario_pre_confirmar`** (POST, Cliente) — Vista previa: valida IDs enteros, que el barbero esté activo y **pertenezca a la peluquería elegida**, `cita_disponible` y `barbero_esta_disponible`; si algo falla, re-renderiza el formulario con el error; si no, muestra `usuario_confirmar_reserva.html` con los datos.
- **`usuario_confirmar_reserva`** (POST, Cliente) — Repite todas las validaciones y además crea la reserva dentro de una **transacción** con `select_for_update` sobre el barbero (revalidando disponibilidad dentro de la transacción para evitar dobles reservas). Crea la reserva, dos notificaciones (barbero y cliente) y envía dos correos. Redirige al inicio.
- **`usuario_perfil`** — GET: perfil, citas (fecha/hora descendente), pedidos, notificaciones y el conjunto de IDs de reservas ya calificadas. POST: edita nombre, apellido, teléfono y foto de perfil.
- **`usuario_cancelar_reserva`** — POST; solo cancela si faltan **≥ 2 horas** para la cita; notifica y envía correos a ambas partes. Si la cita es muy próxima, no cancela y notifica al cliente con el teléfono del barbero.
- **`usuario_editar_reserva`** — GET/POST; no permite editar citas `Cancelada` o `Completada`. Valida barbero activo perteneciente a la sede, disponibilidad de sede y barbero. Al guardar: vuelve el estado a `Pendiente`, notifica al barbero nuevo y al cliente (y **al barbero anterior** si hubo reasignación) y envía correos.
- **`usuario_notificaciones`** — Lista las notificaciones del cliente y los IDs de reservas calificadas.
- **`usuario_marcar_notificaciones_leidas`** — POST; marca todas como leídas.
- **`usuario_confirmar_cita_peluquero`** — POST; para citas creadas **por el barbero**: el cliente pasa la cita a `Confirmada`, marca sus notificaciones de esa reserva como leídas y notifica al barbero.
- **`usuario_calificar`** — POST; solo para citas propias en estado `Completada` y **una sola calificación por reserva** (`OneToOne`); valida puntuación 1–5; crea la `Calificacion` y notifica al barbero.
- **`cambiar_password`** (Cliente o Barbero) — Exige la contraseña actual correcta, coincidencia de la nueva y reglas de seguridad; redirige al perfil según rol.

### 10.4 Barbero

- **`peluquero_dashboard`** — Métricas **cacheadas 20 s**: citas totales, completadas/pendientes/canceladas, citas de hoy, ingresos de hoy y totales (según precios del catálogo); últimas 5 calificaciones, promedio (1 decimal), total de calificaciones; su peluquería (ver §7.3 `_peluqueria_del_barbero`) y su galería.
- **`peluquero_cambiar_estado`** — POST; cambia el estado de una cita **propia** a un valor válido de `Reserva.ESTADOS`; invalida las cachés de métricas (barbero y admin); crea notificación al cliente con mensaje según el estado y envía correos al confirmar o cancelar.
- **`peluquero_perfil`** — GET/POST: edición de nombre, apellido, teléfono y foto; muestra sus citas, calificaciones y el promedio (con `aggregate` en una sola consulta).
- **`peluquero_crear_cita`** — El barbero agenda una cita para un **cliente existente**; valida sede, disponibilidad de sede y barbero; crea la cita en `Pendiente`, notifica y envía correo al cliente con enlace para que la confirme.
- **`peluquero_notificaciones`** — Lista las suyas y las marca **todas** como leídas al abrirlas.
- **`peluquero_crear_peluqueria`** — Solo si aún no tiene una; nombre y ubicación obligatorios; crea la sede con `dueno=usuario` e imagen opcional. Si ya tiene, redirige a editar.
- **`peluquero_editar_peluqueria`** — Edita nombre, ubicación, teléfono, descripción e imagen de su sede.
- **`peluquero_galeria`** — Lista las fotos de su sede.
- **`peluquero_agregar_imagen`** — POST; **máximo 5 fotos** por galería; guarda imagen y descripción.
- **`peluquero_eliminar_imagen`** — Borra la foto **y el archivo físico** (`imagen.delete(save=False)`) solo si pertenece a su sede.

### 10.5 Administrador

- **`admin_dashboard`** — Métricas **cacheadas 20 s**: total de reservas, conteo por cada estado, ventas por servicios completados (precios del catálogo), ventas por pedidos (excluyendo cancelados), total combinado, total de clientes y las 6 últimas reservas.
- **`admin_peluqueros`** — Lista usuarios con rol Barbero.
- **`admin_crear_peluquero`** — Valida campos, email (formato y duplicado), contraseña segura y **peluquería obligatoria**; crea el barbero con peluquería y foto opcional.
- **`admin_editar_peluquero`** — Edita datos, sede y foto; la contraseña solo se actualiza si se envía y cumple las reglas.
- **`admin_eliminar_peluquero`** — **Suspensión** (no borra): pone `activo=False` y, si estaba activo, ejecuta `notificar_suspension_barbero`.
- **`admin_reservas`** — Lista todas las reservas (con `select_related`) ordenadas por fecha/hora.
- **`admin_crear_reserva`** — Reserva manual; valida cliente, barbero activo, sede, servicio y disponibilidad; notifica y envía correos a cliente y barbero.
- **`admin_editar_reserva`** — Edita todos los campos revalidando disponibilidad (excluyendo la propia reserva); notifica y envía correos (mensaje distinto si el estado es Cancelada).
- **`admin_eliminar_reserva`** — Notifica y envía correos a ambas partes y **borra** la reserva.
- **`admin_cancelar_reserva`** — Cancela sin borrar (estado `Cancelada`), con notificaciones y correos.
- **`admin_horarios`** — Gestión por peluquería (selector GET/POST): crea por defecto los 7 días (Lun–Sáb activos, 09:00–18:00) con `get_or_create`; acción `guardar_horarios` guarda activo/inicio/fin de los 7 días; acción `crear_bloqueo` crea un `BloqueoHorario` validando formato de fecha y hora.
- **`admin_eliminar_bloqueo`** — POST; borra un bloqueo.
- **`admin_peluquerias`** / **`admin_crear_peluqueria`** / **`admin_editar_peluqueria`** — CRUD de sedes con imagen y **dueño** (solo barberos válidos).
- **`admin_eliminar_peluqueria`** — **Solo si no tiene reservas asociadas** (protección de integridad); si las tiene, muestra error.
- **`admin_productos`** — Lista productos ordenados por nombre.
- **`admin_crear_producto`** / **`admin_editar_producto`** — Usan `datos_producto` (ver §7.3).
- **`admin_eliminar_producto`** — No borra: pone `stock=0` y `disponible=False` (retirada lógica de la tienda).
- **`admin_mensajes`** — Lista los `MensajeContacto` y marca todos como leídos al abrir la página.
- **`admin_notificaciones`** — Lista las del admin y las marca como leídas.
- **`admin_perfil`** — Edita nombre, apellido y foto; reutiliza el template de perfil con listas vacías.
- **`admin_ingresos`** — Historial de `RegistroIngreso` con filtro por rol (GET `?rol=`).
- **`admin_usuarios`** — Lista todos los usuarios (más recientes primero) con totales por rol.
- **`admin_crear_usuario`** — Valida todo (campos, email, contraseña, duplicados); si el rol es Barbero, **exige peluquería**; crea el usuario con foto opcional.
- **`admin_editar_usuario`** — Edita todo; **el rol de un Admin no se puede modificar**; al pasar a Barbero exige peluquería, al pasar a otro rol limpia la peluquería; contraseña opcional validada.
- **`admin_eliminar_usuario`** — Suspensión (no borra); **no permite suspendersé a uno mismo**; si es barbero activo, notifica suspensión de citas.
- **`admin_suspender_usuario`** — Alterna `activo` (reactivar/suspender); no aplica a admins; notifica suspensión de barberos.
- **`admin_quitar_imagen_producto`** — POST; borra el archivo de la foto del producto y deja el campo vacío.
- **`admin_quitar_foto_peluqueria`** — POST; borra la foto principal de una barbería.
- **`admin_galeria`** — Lista todas las fotos de galería (`ImagenPeluqueria` con `select_related`) para moderarlas.
- **`admin_eliminar_imagen_galeria`** — POST; borra el archivo y el registro de una foto de galería de cualquier barbería.
- **`admin_quitar_foto_usuario`** — POST; borra la foto de perfil de un usuario.
- **`admin_configuracion`** — GET/POST; edita la fila única `Configuracion` (datos generales, privacidad y mantenimiento); valida el correo de contacto y limpia la caché al guardar.

---

## 11. Sistema de notificaciones y correos electrónicos

### 11.1 Notificaciones (modelo `Notificacion`)

Se crean automáticamente en estos eventos:

| Evento | Destinatario(s) |
|---|---|
| Registro de un cliente | Todos los admins activos |
| Mensaje de contacto (ayuda) | Todos los admins activos |
| Stock de un producto llega a 0 | Todos los admins activos |
| Reserva creada (cliente) | Barbero y cliente |
| Reserva creada por barbero | Cliente |
| Reserva creada/editada/cancelada por admin | Cliente y barbero |
| Reserva eliminada por admin | Cliente y barbero |
| Cliente edita su cita | Barbero nuevo, cliente y barbero anterior (si cambió) |
| Cliente cancela cita | Barbero (o aviso al cliente si es muy próxima) |
| Barbero cambia estado de cita | Cliente (mensaje según estado) |
| Barbero suspendido | Clientes con citas futuras (citas vuelven a Pendiente) |
| Calificación recibida | Barbero |
| Pedido confirmado | Cliente (con resumen y total) |
| Cita confirmada por el cliente | Barbero |

### 11.2 Correos (plantilla `emails/notificacion.html`)

- **Formato:** `EmailMultiAlternatives` con versión texto + HTML; **logo embebido** por `Content-ID <tecnocorte-logo>`; `fail_silently=True`.
- **Eventos que envían correo:** bienvenida (registro), recuperación de contraseña, cita agendada (cliente y barbero), cita modificada (cliente, barbero y barbero anterior), cita cancelada (por cliente, barbero o admin), reserva eliminada, cita agendada por barbero/admin, mensaje de contacto al correo oficial, y **foto eliminada por el Admin** (se avisa a quien la subió con el motivo escrito).
- **En desarrollo** los correos se imprimen en la consola (backend `console`).

### 11.3 Moderación de fotos (motivo obligatorio)

Cuando el Admin elimina una **foto** (de producto, de perfil o de galería) el sistema:

1. Exige que se escriba un **motivo** en un modal (campo `motivo`); sin motivo no borra nada y muestra un aviso.
2. Borra el archivo del `ImageField` con `_borrar_archivo` (tolera valores antiguos que eran URLs).
3. Si la foto es de un perfil o de una peluquería, envía un **correo a quien la subió** (`avisar_foto_eliminada`) explicando el motivo.

> El motivo **solo** se exige para fotos; borrar usuarios, barberos, peluquerías o productos sigue usando la confirmación normal.

---

## 12. API REST

### 12.1 ViewSets (`sena/api.py`)

Autenticación común: **`TokenAuthentication` + `SessionAuthentication`**. Permiso personalizado **`ApiPermission`**: requiere sesión web (`session["logueado"]`) o usuario autenticado (token); **lectura** (GET/HEAD/OPTIONS) para cualquier autenticado; **escritura** (POST/PUT/PATCH/DELETE) solo para rol `Admin` o `is_staff`.

| ViewSet | Búsqueda (`search_fields`) | Orden (`ordering_fields`) | Filtrado por rol |
|---|---|---|---|
| `UsuarioViewSet` | nombre, apellido, email, rol | nombre, apellido, fecha_creacion | `get_queryset`: **solo Admin/staff ve usuarios**; otros ven queryset vacío |
| `PeluqueriaViewSet` | nombre, ubicacion | nombre | — (todos los autenticados) |
| `ProductoViewSet` | nombre, categoria | nombre, precio, fecha_creacion | — |
| `ReservaViewSet` | cliente__nombre, peluquero__nombre, peluqueria__nombre, estado | fecha, hora, estado | Admin/staff: todas; Cliente: solo las suyas (`cliente_id`); Barbero: solo las suyas (`peluquero_id`); sin rol válido: ninguna |

`ReservaViewSet` usa `select_related("cliente", "peluquero", "peluqueria")`.

### 12.2 Serializers (`sena/serializers.py`)

- **`UsuarioSerializer`** — campos: id, nombre, apellido, email, password (**write_only**), telefono, rol, fecha_creacion (read_only). `create()` y `update()` cifran la contraseña con `make_password` (solo si se envía).
- **`PeluqueriaSerializer`** — `fields = "__all__"`.
- **`ProductoSerializer`** — `fields = "__all__"`.
- **`ReservaSerializer`** — `cliente` limitado a usuarios con rol `Cliente`; `peluquero` limitado a barberos **activos**; `peluqueria` write_only; campos calculados `cliente_nombre`, `peluquero_nombre`, `peluqueria_nombre`. Validadores: `validate_servicio` (debe estar en `SERVICIOS`), `validate_cliente` (rol Cliente), `validate_peluquero` (rol Barbero y activo).

### 12.3 Seguridad de la API

- Permiso por defecto `IsAuthenticated`.
- Throttling: `anon: 100/day`, `user: 1000/day`.
- Documentación OpenAPI disponible en `/api/schema/`, `/api/docs/` (Swagger) y `/api/redoc/`.

---

## 13. Panel de administración de Django

`sena/admin.py` — los 13 modelos registrados (la ruta `admin/` del proyecto):

| Modelo | `list_display` | `list_filter` | `search_fields` | Notas |
|---|---|---|---|---|
| `Usuario` | nombre, apellido, email, rol, peluqueria, activo, fecha_creacion | rol, activo, peluqueria | nombre, apellido, email | `activo` editable en línea; `password` **excluido** del formulario |
| `Peluqueria` | nombre, ubicacion, telefono | — | nombre | |
| `Producto` | nombre, precio, categoria, stock, disponible | categoria, disponible | nombre | |
| `Reserva` | id, cliente, peluquero, peluqueria, fecha, hora, servicio, estado | estado, fecha | — | |
| `Pedido` | id, cliente, total, estado, fecha | estado | — | |
| `PedidoProducto` | pedido, producto, cantidad, precio | — | — | |
| `RegistroIngreso` | usuario, rol, fecha, ip | — | — | |
| `Notificacion` | usuario, mensaje, leida, fecha | leida | — | |
| `HorarioTrabajo` | peluqueria, día, activo, inicio, fin | peluqueria | — | |
| `BloqueoHorario` | peluqueria, fecha, hora, motivo | peluqueria | — | |
| `MensajeContacto` | nombre, email, asunto, fecha, leido | leido | — | |
| `Calificacion` | cliente, barbero, puntuacion, fecha | puntuacion | — | |
| `Configuracion` | sitio_nombre, registro_abierto, mostrar_telefonos, modo_mantenimiento, actualizado | — | — | Registro único (`pk=1`): no se puede añadir otra fila ni borrarla |

---

## 14. Frontend: plantillas, includes y estáticos

**Enfoque:** sin framework CSS ni build; cada plantilla lleva sus estilos en un bloque `<style>`. Fuentes de Google Fonts cargadas con `preconnect` desde `base/base.html`. **Los menús de Admin y Barbero usan Glassmorphism** (`sena/static/css/includes/panel_glass.css`); el menú del cliente (`site_nav.html`) se mantiene sin cambios. **58 plantillas, ~10.100 líneas.**

### 14.1 Base e includes (14)

| Plantilla | Líneas | Función |
|---|---|---|
| `base/base.html` | 96 | Esqueleto: head con fuentes, bloque `<style>`, bloques `{% block %}` |
| `includes/site_nav.html` | 130 | Navegación del sitio público (cliente) |
| `includes/admin_sidebar.html` | ~215 | Menú lateral del admin (**cristal**) |
| `includes/admin_mobile_nav.html` | ~55 | Navegación móvil del admin (**cristal**) |
| `includes/peluquero_sidebar.html` | ~120 | Menú lateral del barbero (**cristal**) |
| `includes/peluquero_mobile_nav.html` | ~50 | Navegación móvil del barbero (**cristal**) |
| `includes/carrito_indicator.html` | 15 | Contador del carrito (usa `cantidad` del context processor) |
| `includes/notificaciones_indicator.html` | 20 | Campana de notificaciones (usa `notificaciones_no_leidas`) |
| `includes/toast_notifications.html` | ~300 | Mensajes flash tipo toast + modal de **motivo** al borrar fotos |
| `includes/tema.html` | 161 | Selector de tema claro/oscuro |
| `includes/logo.html` | 6 | Logo reutilizable |
| `includes/loading.html` | 61 | Pantalla de carga |
| `includes/cargando.html` | 57 | Variante de carga |
| `emails/notificacion.html` | 149 | Plantilla de correos (diseño oscuro con logo embebido) |

**Hojas de estilo compartidas (`sena/static/css/includes/`):** `panel_glass.css` (Glassmorphism de los paneles Admin/Barbero), `toast_notifications.css` (toasts + modal de motivo), `tema.css`, `loading.css`.

### 14.2 Públicas (8) — `templates/publicos/`

`index.html` (301), `login.html` (211), `registro.html` (235), `recuperar_password.html` (46), `restablecer_password.html` (52), `como_funciona.html` (21), `sobre_nosotros.html` (18), `ayuda.html` (232).

### 14.3 Carrito (3) — `templates/carrito/`

`carrito.html` (432, con operaciones AJAX), `finalizar_pedido.html` (198), `pedido_exitoso.html` (77).

### 14.4 Cliente (12) — `templates/usuarios/`

`usuario_tienda.html` (617), `usuario_servicios.html` (540), `usuario_reservar_cita.html` (636, con calendario JS), `usuario_confirmar_reserva.html` (221), `usuario_perfil.html` (506), `usuario_peluquerias.html` (273), `usuario_peluqueria_detalle.html` (192), `usuario_notificaciones.html` (208), `usuario_editar_reserva.html` (82), `cambiar_password.html` (98), `dashboard_base.html` (179, base del panel de cliente).

### 14.5 Barbero (6) — `templates/peluqueros/`

`peluquero_dashboard.html` (475), `peluquero_perfil.html` (301), `peluquero_crear_cita.html` (160), `peluquero_galeria.html` (139), `peluquero_editar_peluqueria.html` (96), `peluquero_notificaciones.html` (68). *(Se eliminó `peluquero_crear_peluqueria.html`: el barbero ya no crea su propia peluquería.)*

### 14.6 Admin (17) — `templates/administrador/`

`admin_usuarios.html` (292), `admin_listar_peluqueros.html` (238), `admin_formulario_reserva.html` (192), `admin_listar_reservas.html` (202), `admin_horarios.html` (176), `admin_formulario_usuario.html` (220), `admin_formulario_peluquero.html` (143), `admin_dashboard.html` (86), `admin_formulario_peluqueria.html` (91), `admin_listar_ingresos.html` (105), `admin_perfil.html` (91), `admin_productos.html` (79), `admin_formulario_producto.html` (73), `admin_peluquerias.html` (57), `admin_notificaciones.html` (38), `admin_mensajes.html` (36).

### 14.7 JavaScript en el frontend

- **Calendario de reservas** (`usuario_reservar_cita.html`, ~636 líneas): recibe `horarios_json`, `bloqueos_json`, `reservas_json`, `fecha_hoy` y `hora_actual` desde la vista; muestra solo horas disponibles.
- **Carrito AJAX** (`carrito.html`, `usuario_tienda.html`): agregar/actualizar/eliminar con respuestas JSON del backend.

---

## 15. Base de datos y migraciones

- **Migraciones:** 23 archivos en `sena/migrations/`, **todas aplicadas** (verificado con `showmigrations` sobre `db_temporal.sqlite3`). No hay pendientes.

| # | Migración | Contenido |
|---|---|---|
| 0001 | `initial` | Modelo inicial (Usuario, Peluqueria, Reserva, Servicio...) |
| 0002 | `producto` | Modelo Producto |
| 0003 | `remove_producto_imagen_url` | Elimina `imagen_url` del producto |
| 0004 | `alter_reserva_estado` | Cambia choices de estado de Reserva |
| 0005 | `pedido_reserva_servicio_pedidoproducto` | Pedido, PedidoProducto y cambios en Reserva/Servicio |
| 0006 | `registroingreso` | Historial de ingresos |
| 0007 | `notificacion` | Modelo Notificacion |
| 0008 | `cambiar_peluquero_a_barbero` | Renombra rol "Peluquero" → "Barbero" |
| 0009 | `actualizar_roles_peluquero_a_barbero` | Actualiza datos de roles |
| 0010 | `horariotrabajo_bloqueohorario` | Horarios y bloqueos |
| 0011 | `mensajecontacto` | Mensajes de contacto |
| 0012 | `reserva_completada` | Estado "Completada" en Reserva |
| 0013 | `calificacion` | Modelo Calificacion |
| 0013 | `producto_imagen` | Imagen como URLField |
| 0014 | `usuario_activo` | Campo `activo` (suspensiones) |
| 0015 | `alter_horariotrabajo_options_and_more` | Meta options de HorarioTrabajo |
| 0016 | `bloqueohorario_peluqueria` | Peluquería en bloqueos |
| 0017 | `merge_20260820_1340` | Merge de ramas de migración |
| 0018 | `migrar_passwords` | **Migra contraseñas en claro a hash** |
| 0019 | `proteger_relaciones` | Cambia `on_delete` a PROTECT en reservas/pedidos |
| 0020 | `alter_usuario_password` | Aumenta longitud del campo password a 128 |
| 0021 | `usuario_foto_usuario_peluqueria` | Foto de perfil y campos de peluquería |
| 0021 | `agregar_peluqueria_dueno_galeria` | Dueño de peluquería e ImagenPeluqueria |
| 0022 | `merge_20260921_1502` | Segundo merge de ramas |
| 0023 | `bloqueohorario_sena_bloque_peluque_6274c6_idx_and_more` | Índices de bloqueos y otros |
| 0024 | `configuracion_alter_producto_imagen` | **`Producto.imagen` pasa a `ImageField`** y modelo `Configuracion` |
| 0025 | `configuracion_inicial` | Datos iniciales de `Configuracion` (singleton) |

- **Nota:** existen **dos ramas de migraciones paralelas** (dos `0013`, dos `0021`) resueltas con merges `0017` y `0022`.
- **Base local:** `db_temporal.sqlite3` (282 KB, ignorada por Git).
- **Base de producción:** PostgreSQL con SSL (Supabase/Supavisor), según `.env`.

---

## 16. Tests (pruebas automatizadas)

`sena/tests.py` — clase **`TecnoCorteTests(TestCase)`**, 8 pruebas. `setUp` crea: un cliente, un barbero, una peluquería ("Barbería Test") y un horario de lunes 9:00–18:00. Incluye el helper `iniciar_sesion()` que simula la sesión.

| # | Test | Qué verifica |
|---|---|---|
| 1 | `test_inicio_muestra_inicio_al_cliente_logueado` | Un cliente logueado ve `/` con `publicos/index.html` (200 OK) |
| 2 | `test_peluquerias_sin_imagen_muestran_logo` | Las peluquerías sin imagen muestran `sena/images/Logo.png` |
| 3 | `test_login_usa_password_hasheada` | Login POST con contraseña hasheada redirige al inicio |
| 4 | `test_registro_envia_correo_con_diseno_html` | El registro envía **1 correo** con versión HTML, estilo `background:#090909` y logo embebido (`Content-ID: <tecnocorte-logo>`) |
| 5 | `test_no_permite_reservar_fecha_pasada` | `cita_disponible` rechaza fechas pasadas (mensaje con "pasada") |
| 6 | `test_cliente_no_entra_a_panel_admin` | Un cliente accediendo a `admin_dashboard` es redirigido al login |
| 7 | `test_cambio_password_usa_la_cuenta_de_la_sesion` | Cambio de contraseña: muestra el email correcto, redirige al perfil y actualiza el hash |
| 8 | `test_mensaje_de_ayuda_llega_al_correo_oficial_y_al_panel` | El formulario de ayuda envía correo a `tecnocorte083@gmail.com` con el asunto y crea notificación para el admin |
| 9 | `test_serializer_incluye_y_valida_servicio` | `ReservaSerializer` incluye el campo `servicio` y rechaza un servicio inexistente |

**`sena/tests_fotos.py` — `FotosYConfiguracionTests(TestCase)`, 21 pruebas** (fotos de producto, moderación de imágenes, configuración, motivo de borrado + correo, alta de barberos y render de los paneles de cristal). Incluyen un `tearDown` que limpia la caché de `Configuracion` (se cachea 300 s) para no filtrar estado entre pruebas. Ejecutar todo con:

```bash
DJANGO_SETTINGS_MODULE=tecnocorte.settings_local python manage.py test sena --noinput
```

---

## 17. Historial de Git

Repositorio: `origin → https://github.com/tecnocorte-barber/TecnoCorte_proyecto.git`. Rama `main`, 15 commits, **árbol limpio** (sin cambios locales ni archivos sin seguimiento).

| Commit | Mensaje |
|---|---|
| `1834b59` | Agregar settings_local con SQLite para desarrollo local ← **HEAD** |
| `4233e72` | Eliminar .idea del repositorio y agregarlo a .gitignore |
| `4953718` | eliminar dependencias de node |
| `5765509` | bueno |
| `c4e50e4` | diseño responsive, corrección de errores y permisos por rol |
| `b4a0919` | mejoras y optimizacion |
| `cc01b86` | arreglo de lineas, base de datos |
| `30140ca` | Enviar correos. contrastes tema claro, |
| `0175c31` | Horarios, citas, landing |
| `25132b1` | Cambio now date a local date |
| `6394af6` | agregar comentarios explicativos a settings |
| `34d4060` | limpieza de comentarios en settings |
| `4a5d51e` | comentarios, menu hamburguesa, contraseña segura, correo no repetido |
| `f6fd76c` | Validaciones y seguridad para ingresos con roles |
| `74eeee9` | Mejoras y temas |

---

## 18. Optimizaciones de rendimiento

1. **Caché (Django cache framework):**
   - Contadores de notificaciones y mensajes: **20 s** (context processor).
   - Métricas del dashboard del barbero: **20 s** por barbero (clave `barbero_dashboard_metricas_<id>`).
   - Métricas del dashboard del admin: **20 s** (clave `admin_dashboard_metricas`); se invalidan al cambiar estado de una cita.
   - Intentos de login (anti fuerza bruta): 300 s.
2. **`CONN_MAX_AGE = 60`** en PostgreSQL (reutiliza conexiones frente a la latencia del pooler remoto).
3. **`select_related`** en listas pesadas: reservas del admin y del barbero, calificaciones, registros de ingreso, reservas de la API.
4. **`select_for_update`** dentro de transacciones para reservas y pedidos (evita condiciones de carrera).
5. **`aggregate`** en una sola consulta para el promedio de calificaciones del barbero.
6. **`only(...)`** en `_reservas_para_template` (carga solo los campos necesarios del calendario).
7. **`prepare_threshold: None`** para compatibilidad con el pooler transaccional (evita errores y reintentos).

---

## 19. Seguridad implementada

- **Contraseñas:** hash con `make_password`/`check_password` (PBKDF2 de Django); campo de 128 caracteres; la migración `0018` migró datos en claro; reglas propias (8+ caracteres, mayúscula, número, símbolo) aplicadas en registro, recuperación, cambio y CRUD del admin.
- **Autorización:** decorador `@autorizacion(roles)` en todas las vistas privadas; además valida que la cuenta siga **activa** en cada petición.
- **Anti fuerza bruta:** 5 intentos fallidos → bloqueo de 5 minutos por correo+IP (caché).
- **Recuperación de contraseña:** token firmado (HMAC con sal), expiración de 1 hora, invalidado al cambiar la contraseña; comparación con `hmac.compare_digest`.
- **Cookies:** `SESSION_COOKIE_SECURE` y `CSRF_COOKIE_SECURE` en producción; CSRF middleware activo en todos los formularios.
- **Redirecciones `next`:** validadas con `url_has_allowed_host_and_scheme` (previene open redirect).
- **Validación de IDs:** `_id_entero` evita valores no numéricos en parámetros de URL/POST.
- **Inyección de cabeceras:** el asunto del correo de ayuda limpia `\r\n`.
- **API:** `IsAuthenticated` por defecto, permiso por rol, throttling, contraseña write-only.
- **Integridad referencial:** `PROTECT` en reservas/pedidos; el admin de Django oculta `password`; no se pueden eliminar peluquerías con reservas ni usuarios desde el propio admin de la app (suspensión en su lugar).
- **Aislamiento de carritos** por cuenta en la sesión.

---

## 20. Observaciones y mejoras sugeridas

Estas observaciones se derivan de la lectura del código, no de errores detectados en ejecución:

1. **`views.py` monolítico (1.955 líneas):** toda la lógica web está en un archivo. Sugerencia: dividir en módulos (`autenticacion.py`, `carrito.py`, `reservas.py`, `cliente.py`, `barbero.py`, `admin.py`).
2. **No hay `forms.py`:** todos los formularios se validan manualmente con `request.POST`; migrar a `django.forms` o `ModelForm` reduciría duplicación y riesgo de olvidos.
3. **Autenticación propia en lugar de `django.contrib.auth`:** no aprovecha sesiones de Django, permisos por objeto ni el admin de usuarios integrado. Es una decisión válida pero con costos de mantenimiento.
4. **`Producto.imagen` es `URLField`:** a pesar de existir la migración `0013_producto_imagen`, el modelo actual apunta a imágenes externas; las subidas (`ImageField`) solo se usan en fotos de perfil, sedes y galerías.
5. **Estilos inline duplicados:** al eliminar las dependencias de Node se perdieron los archivos CSS compartidos; hay estilos repetidos entre plantillas. Sugerencia: recuperar un `sena.css` estático único.
6. **API incompleta:** no hay endpoints para pedidos, notificaciones, calificaciones ni horarios.
7. **SPECTACULAR_SETTINGS sin personalizar:** título "Mi API" y descripción genérica; debería decir "TecnoCorte".
8. **`usuario_dashboard` es idéntica a `usuario_tienda`:** ambas renderizan la misma plantilla.
9. **Dos migraciones con el mismo número (0013 y 0021):** resueltas con merges; convendría limpiar el historial si el proyecto aún está en desarrollo.
10. **`Documento ignorado`:** `DOCUMENTACION_PROYECTO.md` está en `.gitignore` (documentación externa no versionada).

---

## 21. Cómo ejecutar el proyecto

```bash
# 1. Activar el entorno virtual (ya existe en la raíz)
source .venv/bin/activate

# 2. Desarrollo local con SQLite (db_temporal.sqlite3, ya migrada)
export DJANGO_SETTINGS_MODULE=tecnocorte.settings_local
python manage.py runserver

# 3. (Opcional) Crear superusuario para el admin de Django
python manage.py createsuperuser

# 4. Ejecutar los tests
python manage.py test sena
```

**Producción** (con `tecnocorte.settings` y PostgreSQL): requiere definir en el entorno (o `.env`) las claves `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`, y las de correo `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`. Luego:

```bash
python manage.py migrate
python manage.py collectstatic
```

**Puntos de acceso clave tras arrancar:**

- Landing pública: `/`
- Login: `/login/` · Registro: `/registro/`
- Tienda/carrito: `/carrito/` y `/usuario/tienda/`
- Panel cliente: `/usuario/dashboard/` · Barbero: `/peluquero/dashboard/` · Admin: `/admin/dashboard/`
- Admin de Django: `/admin/` · API: `/api/` · Swagger: `/api/docs/` · Redoc: `/api/redoc/`
