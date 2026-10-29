# Modelos de la base de datos de TecnoCorte (barbería):
# usuarios, peluquerías, productos, reservas, pedidos, notificaciones, horarios y calificaciones.
from django.db import models
from django.db.models import Q

# Usuario del sistema con rol Admin, Barbero o Cliente
class Usuario(models.Model):
    ROLES = (
        ("SuperAdmin", "SUPER ADMINISTRADOR"),
        ("Admin", "ADMINISTRADOR"),
        ("Barbero", "BARBERO"),
        ("Cliente", "CLIENTE"),
    )
    
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    telefono = models.CharField(max_length=20, blank=True)
    rol = models.CharField(max_length=15, choices=ROLES, default="Cliente")
    # Peluquería a la que pertenece el usuario (obligatoria solo para barberos)
    peluqueria = models.ForeignKey(
        "Peluqueria",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios",
    )
    # Foto de perfil. Se sube desde los formularios de edición de perfil.
    foto = models.ImageField(upload_to="fotos_perfil/", blank=True, null=True)
    # ── Preferencias de notificación (Configuración del cliente y del barbero) ──
    aviso_correo = models.BooleanField(
        default=True,
        help_text="Recibir recordatorios de citas por correo.",
    )
    aviso_whatsapp = models.BooleanField(
        default=False,
        help_text="Recibir recordatorios de citas por WhatsApp.",
    )
    aviso_sms = models.BooleanField(
        default=False,
        help_text="Recibir recordatorios de citas por SMS.",
    )
    aviso_anticipacion_horas = models.PositiveSmallIntegerField(
        default=24,
        help_text="Horas de anticipación con las que se envía el recordatorio.",
    )
    # Cambia al modificar la contraseña para invalidar todas las sesiones
    # anteriores de la cuenta sin depender de Django Auth.
    sesion_version = models.PositiveIntegerField(default=1)
    # Verificación de correo: el código se almacena como hash y expira.
    # Las cuentas antiguas quedan verificadas para no bloquear usuarios existentes.
    email_verificado = models.BooleanField(default=True)
    codigo_verificacion_hash = models.CharField(max_length=128, blank=True, default="")
    codigo_verificacion_expira = models.DateTimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.nombre} - {self.rol}"

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)


class RegistroPendiente(models.Model):
    """Datos de registro que aún no se convierten en una cuenta activa.

    La contraseña se almacena ya cifrada y los códigos nunca se guardan en
    texto plano. Esto permite completar la verificación desde otro navegador
    o después de reiniciar el servidor.
    """
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    telefono = models.CharField(max_length=20, blank=True)
    codigo_hash = models.CharField(max_length=64)
    codigo_expira = models.DateTimeField()
    token_hash = models.CharField(max_length=64, unique=True)
    token_expira = models.DateTimeField()
    ultimo_envio = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["email"]), models.Index(fields=["token_hash"])]

    def __str__(self):
        return f"Registro pendiente: {self.email}"

# Sede o barbería donde se atienden las citas
class Peluqueria(models.Model):
    nombre = models.CharField(max_length=100)
    ubicacion = models.CharField(max_length=200)
    telefono = models.CharField(max_length=20)
    dueno = models.ForeignKey("Usuario", on_delete=models.SET_NULL, null=True, blank=True, related_name="peluquerias_dueno")
    descripcion = models.TextField(blank=True, default="")
    imagen = models.ImageField(upload_to="peluquerias/", blank=True)
    
    def __str__(self):
        return self.nombre


# Fotos de la galería de cada peluquería
class ImagenPeluqueria(models.Model):
    peluqueria = models.ForeignKey(Peluqueria, on_delete=models.CASCADE, related_name="galeria")
    imagen = models.ImageField(upload_to="galeria/")
    descripcion = models.CharField(max_length=200, blank=True, default="")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Foto {self.id} - {self.peluqueria.nombre}"

# Producto de la tienda con precio, stock y categoría
class Producto(models.Model):
    CATEGORIAS = (
        ("Herramientas", "Herramientas"),
        ("Fijacion", "Fijación & Textura"),
        ("Cuidado", "Cuidado Capilar"),
        ("Barba", "Barba & Afeitado"),
    )
    
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    precio = models.IntegerField()
    # Foto del producto: la sube el Admin desde el panel y queda ligada a la base.
    # max_length amplio para no romper valores antiguos que eran URLs.
    imagen = models.ImageField(upload_to="productos/", blank=True, default="", max_length=500)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default="Herramientas")
    stock = models.IntegerField(default=0)
    disponible = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["disponible"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(precio__gte=0), name="producto_precio_no_negativo"),
            models.CheckConstraint(condition=Q(stock__gte=0), name="producto_stock_no_negativo"),
        ]

    def __str__(self):
        return self.nombre

# Cita que un cliente reserva con un barbero en una peluquería
class Reserva(models.Model):
    ESTADOS = (
        ("Pendiente", "Pendiente"),
        ("Confirmada", "Confirmada"),
        ("Completada", "Completada"),
        ("Cancelada", "Cancelada"),
    )

    cliente = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="reservas_cliente")
    peluquero = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="reservas_peluquero")
    peluqueria = models.ForeignKey(Peluqueria, on_delete=models.PROTECT)
    fecha = models.DateField()
    hora = models.TimeField()
    servicio = models.CharField(max_length=100, blank=True, default="Corte de Cabello")
    estado = models.CharField(max_length=20, choices=ESTADOS, default="Pendiente")
    # Se guarda el momento del recordatorio para que el comando periódico no
    # envíe el mismo correo varias veces para una misma cita.
    recordatorio_correo_enviado = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["peluquero", "fecha"]),
            models.Index(fields=["cliente", "fecha"]),
            models.Index(fields=["estado"]),
        ]
    
    def __str__(self):
        return f"Reserva {self.id}"

# Compra de productos hecha por un cliente
class Pedido(models.Model):
    ESTADOS = (
        ("Pendiente", "Pendiente"),
        ("Listo", "Listo para recoger"),
        ("Entregado", "Entregado"),
        ("Completado", "Completado"),
        ("Cancelado", "Cancelado"),
    )

    cliente = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="pedidos")
    fecha = models.DateTimeField(auto_now_add=True)
    total = models.IntegerField(default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="Pendiente")
    # La tienda cobra al recoger. El pago se registra aparte del estado de
    # preparación para que el Admin pueda marcarlo sin alterar el pedido.
    pago_confirmado = models.BooleanField(default=False)
    fecha_pago = models.DateTimeField(null=True, blank=True)
    fecha_entrega = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(total__gte=0), name="pedido_total_no_negativo"),
        ]

    def __str__(self):
        return f"Pedido {self.id} - {self.cliente.nombre}"

# Detalle de cada producto incluido en un pedido
class PedidoProducto(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="productos")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="pedidos_productos")
    cantidad = models.IntegerField(default=1)
    precio = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="pedido_producto_cantidad_positiva"),
            models.CheckConstraint(condition=Q(precio__gte=0), name="pedido_producto_precio_no_negativo"),
        ]

    def __str__(self):
        return f"{self.producto.nombre} x{self.cantidad}"

# Historial de inicios de sesión de los usuarios
class RegistroIngreso(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="ingresos")
    rol = models.CharField(max_length=15)
    fecha = models.DateTimeField(auto_now_add=True)
    ip = models.CharField(max_length=45, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["usuario", "fecha"]),
        ]

    def __str__(self):
        return f"{self.usuario.nombre} ({self.rol}) - {self.fecha}"


class JWTRefreshToken(models.Model):
    """Refresh token vigente; solo se almacena el hash del identificador."""
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="refresh_tokens")
    jti_hash = models.CharField(max_length=64, unique=True)
    expira = models.DateTimeField()
    revocado = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)
    revocado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["usuario", "revocado"]), models.Index(fields=["expira"]) ]

# Aviso que recibe un usuario sobre sus citas o pedidos
class Notificacion(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="notificaciones")
    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, null=True, blank=True, related_name="notificaciones")
    mensaje = models.CharField(max_length=255)
    leida = models.BooleanField(default=False)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["usuario", "leida"]),
        ]

    def __str__(self):
        return f"Notificacion {self.id} - {self.usuario.nombre}"


# Horario de atención semanal de cada peluquería (lo configura el Admin)
class HorarioTrabajo(models.Model):
    """Horario general que configura el administrador para cada día y cada peluquería."""
    DIAS = (
        (0, "Lunes"), (1, "Martes"), (2, "Miércoles"),
        (3, "Jueves"), (4, "Viernes"), (5, "Sábado"), (6, "Domingo"),
    )

    peluqueria = models.ForeignKey(Peluqueria, on_delete=models.CASCADE, related_name="horarios", default=1)
    dia_semana = models.PositiveSmallIntegerField(choices=DIAS)
    activo = models.BooleanField(default=True)
    hora_inicio = models.TimeField(default="09:00")
    hora_fin = models.TimeField(default="18:00")

    class Meta:
        unique_together = ("peluqueria", "dia_semana")
        ordering = ["dia_semana"]

    def __str__(self):
        return f"{self.peluqueria.nombre} - {self.get_dia_semana_display()}"


# Día u hora bloqueada para no recibir citas (lo configura el Admin)
class BloqueoHorario(models.Model):
    """Bloquea un día completo o una hora específica para las citas de una peluquería."""
    peluqueria = models.ForeignKey(Peluqueria, on_delete=models.CASCADE, related_name="bloqueos", default=1)
    fecha = models.DateField()
    hora = models.TimeField(null=True, blank=True)
    motivo = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["fecha", "hora"]
        indexes = [
            models.Index(fields=["peluqueria", "fecha"]),
        ]

    def __str__(self):
        if self.hora:
            return f"{self.peluqueria.nombre} - {self.fecha} {self.hora}"
        return f"{self.peluqueria.nombre} - {self.fecha} (todo el día)"


# Opciones de tipo de mensaje que reemplazan el "asunto" de texto libre del
# formulario de contacto. Se usan en el dropdown del formulario y en la tabla
# de mensajes del panel de administración.
TIPOS_MENSAJE = [
    ("consulta", "Consulta general"),
    ("soporte", "Soporte técnico"),
    ("cita", "Problema con una cita"),
    ("pedido", "Pedidos y tienda"),
    ("cuenta", "Cuenta y acceso"),
    ("denuncia", "Denuncia o queja"),
    ("otro", "Otro"),
]
TIPOS_MENSAJE_DICCIONARIO = dict(TIPOS_MENSAJE)


# Mensaje enviado desde el formulario de contacto de la página de ayuda
class MensajeContacto(models.Model):
    nombre = models.CharField(max_length=100)
    email = models.EmailField()
    asunto = models.CharField(max_length=150)
    tipo = models.CharField(
        max_length=20,
        choices=TIPOS_MENSAJE,
        default="consulta",
        help_text="Categoría del mensaje (dropdown del formulario de contacto).",
    )
    mensaje = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)
    leido = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["leido"]),
        ]

    def __str__(self):
        return f"{self.asunto} - {self.nombre}"


# Calificación de 1 a 5 que el cliente da al barbero tras una cita completada
class Calificacion(models.Model):
    # La reserva y el barbero son opcionales: una reseña puede nacer de una cita
    # completada o escribirse directamente desde la portada.
    reserva = models.OneToOneField(Reserva, on_delete=models.CASCADE, related_name="calificacion", null=True, blank=True)
    cliente = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="calificaciones_hechas")
    barbero = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="calificaciones_recibidas", null=True, blank=True)
    puntuacion = models.PositiveSmallIntegerField()
    comentario = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        constraints = [
            models.CheckConstraint(condition=Q(puntuacion__gte=1, puntuacion__lte=5), name="calificacion_entre_1_y_5"),
        ]

    def __str__(self):
        destino = self.barbero.nombre if self.barbero else "TecnoCorte"
        return f"{self.cliente.nombre} → {destino} ({self.puntuacion}/5)"


# Configuración general del sitio: privacidad, datos de contacto y mantenimiento.
# Es un registro único (siempre pk=1) que administra el Admin desde su panel.
class Configuracion(models.Model):
    # ── Datos generales ──
    sitio_nombre = models.CharField(max_length=100, default="TecnoCorte")
    correo_contacto = models.EmailField(default="tecnocorte083@gmail.com")
    texto_aviso = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Aviso corto que se muestra a los visitantes (opcional).",
    )

    # ── Privacidad ──
    registro_abierto = models.BooleanField(
        default=True,
        help_text="Permite que cualquier persona cree una cuenta de cliente.",
    )
    mostrar_telefonos = models.BooleanField(
        default=True,
        help_text="Muestra el teléfono de las barberías a los visitantes.",
    )
    mostrar_ubicaciones = models.BooleanField(
        default=True,
        help_text="Muestra la ubicación de las barberías a los visitantes.",
    )
    mostrar_galeria = models.BooleanField(
        default=True,
        help_text="Muestra la galería de fotos de las barberías al público.",
    )
    mostrar_calificaciones = models.BooleanField(
        default=True,
        help_text="Muestra las calificaciones de los barberos.",
    )

    # ── Mantenimiento ──
    modo_mantenimiento = models.BooleanField(
        default=False,
        help_text="Si se activa, solo el Admin puede navegar el sitio.",
    )
    mensaje_mantenimiento = models.CharField(
        max_length=200,
        blank=True,
        default="Estamos realizando mejoras. Volvemos pronto.",
    )

    # ── Contenido destacado del inicio ──
    # El Admin los cambia con el botón "Editar inicio" de la página principal.
    # Se guarda el nombre del servicio (igual que en Reserva.servicio) para poder
    # destacar tanto los del sistema como los que los barberos piden y se aprueban.
    servicio_destacado_1 = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Servicio de la primera tarjeta destacada del inicio.",
    )
    servicio_destacado_2 = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Servicio de la segunda tarjeta destacada del inicio.",
    )
    producto_destacado_1 = models.ForeignKey(
        "Producto",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Producto destacado principal",
        help_text="Producto grande de la tienda en el inicio.",
    )
    producto_destacado_2 = models.ForeignKey(
        "Producto",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Producto destacado secundario",
        help_text="Segundo producto de la tienda en el inicio.",
    )

    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración"
        verbose_name_plural = "Configuración"

    def __str__(self):
        return "Configuración del sitio"

    def save(self, *args, **kwargs):
        # Solo existe una fila de configuración: siempre se guarda con pk=1.
        self.pk = 1
        super().save(*args, **kwargs)
        # Se limpia la caché para que el cambio se vea de inmediato.
        from django.core.cache import cache

        cache.delete("configuracion_sitio")

    @classmethod
    def cargar(cls):
        """Devuelve la configuración (creando la fila si no existe) usando caché corta."""
        from django.core.cache import cache

        config = cache.get("configuracion_sitio")
        if config is None:
            config, _ = cls.objects.get_or_create(pk=1)
            cache.set("configuracion_sitio", config, 300)
        return config


# Error inesperado del sistema. Guarda lo suficiente para reproducirlo y avisa al
# Admin, sin filtrar nunca esos detalles a la persona que navega.
class RegistroError(models.Model):
    ESTADOS = (
        ("pendiente", "Pendiente"),
        ("revisado", "Revisado"),
    )

    codigo = models.CharField(
        max_length=12,
        unique=True,
        help_text="Código corto que se muestra a la persona afectada.",
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    codigo_http = models.PositiveSmallIntegerField(default=500)
    ruta = models.CharField(max_length=300)
    metodo = models.CharField(max_length=10)
    tipo = models.CharField(max_length=150, help_text="Clase de la excepción.")
    mensaje = models.TextField(help_text="Texto del error, recortado a un tamaño razonable.")
    detalle = models.TextField(blank=True, help_text="Traza completa para depurar.")
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="errores",
    )
    ip = models.CharField(max_length=45, blank=True)
    navegador = models.CharField(max_length=200, blank=True)
    notificado = models.BooleanField(default=False, help_text="Si ya se avisó a los Admin.")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["estado", "-fecha"]),
        ]

    def __str__(self):
        return f"[{self.codigo}] {self.tipo} en {self.ruta}"

    @property
    def titulo(self):
        """Frase corta para el asunto del correo y la notificación."""
        if self.codigo_http == 404:
            return "Página no encontrada"
        if self.codigo_http == 403:
            return "Acceso denegado"
        return "Error inesperado del sitio"


class RegistroAccion(models.Model):
    """Auditoría de acciones sensibles realizadas dentro de la plataforma."""

    actor = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acciones_realizadas",
    )
    accion = models.CharField(max_length=80)
    entidad = models.CharField(max_length=80, blank=True, default="")
    entidad_id = models.PositiveIntegerField(null=True, blank=True)
    detalle = models.CharField(max_length=500, blank=True, default="")
    ip = models.CharField(max_length=45, blank=True)
    navegador = models.CharField(max_length=200, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["accion", "-fecha"]),
            models.Index(fields=["actor", "-fecha"]),
        ]

    def __str__(self):
        nombre = self.actor.email if self.actor else "sistema"
        return f"{nombre}: {self.accion} ({self.fecha:%Y-%m-%d %H:%M})"


# ============================================================================
# Servicios propios de un barbero
# ----------------------------------------------------------------------------
# El barbero no crea servicios directamente: envía una SOLICITUD y el Admin la
# resuelve. Si la aprueba, se crea el servicio a nombre de ese barbero; si la
# rechaza, se guarda el motivo.
# ============================================================================
class Servicio(models.Model):
    """Servicio que ofrece un barbero concreto (nace de una solicitud aprobada)."""

    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=300, blank=True, default="")
    duracion = models.CharField(max_length=50, default="30 Minutos")
    minutos = models.PositiveSmallIntegerField(default=30)
    precio = models.PositiveIntegerField(default=0)
    barbero = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="servicios"
    )
    peluqueria = models.ForeignKey(
        Peluqueria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="servicios",
    )
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Servicio del barbero"
        verbose_name_plural = "Servicios de barberos"
        constraints = [
            models.UniqueConstraint(
                fields=["barbero", "nombre"], name="servicio_unico_por_barbero"
            ),
        ]

    def __str__(self):
        return f"{self.nombre} - {self.barbero_id}"

    def a_dict(self):
        """Mismo formato que la lista SERVICIOS que consume la reserva."""
        return {
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "duracion": self.duracion,
            "minutos": self.minutos,
            "precio": self.precio,
        }


class SolicitudServicio(models.Model):
    """Petición del barbero para que el Admin le cree un servicio nuevo."""

    ESTADOS = (
        ("pendiente", "Pendiente"),
        ("aprobada", "Aprobada"),
        ("rechazada", "Rechazada"),
        ("eliminada", "Eliminada"),
    )

    barbero = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="solicitudes_servicio"
    )
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=300, blank=True, default="")
    duracion = models.CharField(max_length=50, default="30 Minutos")
    minutos = models.PositiveSmallIntegerField(default=30)
    precio = models.PositiveIntegerField(default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    nota_admin = models.CharField(max_length=300, blank=True, default="")
    creada = models.DateTimeField(auto_now_add=True)
    resuelta = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creada"]
        verbose_name = "Solicitud de servicio"
        verbose_name_plural = "Solicitudes de servicio"
        indexes = [
            models.Index(fields=["estado", "-creada"]),
        ]

    def __str__(self):
        return f"{self.nombre} - {self.get_estado_display()} ({self.barbero_id})"

    @property
    def pendiente(self):
        return self.estado == "pendiente"
