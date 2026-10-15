# Modelos de la base de datos de TecnoCorte (barbería):
# usuarios, peluquerías, productos, reservas, pedidos, notificaciones, horarios y calificaciones.
from django.db import models

# Usuario del sistema con rol Admin, Barbero o Cliente
class Usuario(models.Model):
    ROLES = (
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
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.nombre} - {self.rol}"

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
        ("Pagado", "Pagado"),
        ("Entregado", "Entregado"),
        ("Cancelado", "Cancelado"),
    )

    cliente = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="pedidos")
    fecha = models.DateTimeField(auto_now_add=True)
    total = models.IntegerField(default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="Pendiente")

    def __str__(self):
        return f"Pedido {self.id} - {self.cliente.nombre}"

# Detalle de cada producto incluido en un pedido
class PedidoProducto(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="productos")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="pedidos_productos")
    cantidad = models.IntegerField(default=1)
    precio = models.IntegerField(default=0)

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


# Mensaje enviado desde el formulario de contacto de la página de ayuda
class MensajeContacto(models.Model):
    nombre = models.CharField(max_length=100)
    email = models.EmailField()
    asunto = models.CharField(max_length=150)
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
    reserva = models.OneToOneField(Reserva, on_delete=models.CASCADE, related_name="calificacion")
    cliente = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="calificaciones_hechas")
    barbero = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="calificaciones_recibidas")
    puntuacion = models.PositiveSmallIntegerField()
    comentario = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.cliente.nombre} → {self.barbero.nombre} ({self.puntuacion}/5)"


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
