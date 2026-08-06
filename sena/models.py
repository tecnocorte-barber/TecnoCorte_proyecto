from django.db import models

class Usuario(models.Model):
    ROLES = (
        ("Admin", "ADMINISTRADOR"),
        ("Peluquero", "PELUQUERO"),
        ("Cliente", "CLIENTE"),
    )
    
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, blank=True)
    rol = models.CharField(max_length=15, choices=ROLES, default="Cliente")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.nombre} - {self.rol}"

class Peluqueria(models.Model):
    nombre = models.CharField(max_length=100)
    ubicacion = models.CharField(max_length=200)
    telefono = models.CharField(max_length=20)
    
    def __str__(self):
        return self.nombre

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
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default="Herramientas")
    stock = models.IntegerField(default=0)
    disponible = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class Reserva(models.Model):
    ESTADOS = (
        ("Pendiente", "Pendiente"),
        ("Confirmada", "Confirmada"),
        ("Cancelada", "Cancelada"),
    )

    cliente = models.ForeignKey(Usuario, on_delete=models.DO_NOTHING, related_name="reservas_cliente")
    peluquero = models.ForeignKey(Usuario, on_delete=models.DO_NOTHING, related_name="reservas_peluquero")
    peluqueria = models.ForeignKey(Peluqueria, on_delete=models.DO_NOTHING)
    fecha = models.DateField()
    hora = models.TimeField()
    servicio = models.CharField(max_length=100, blank=True, default="Corte de Cabello")
    estado = models.CharField(max_length=20, choices=ESTADOS, default="Pendiente")
    
    def __str__(self):
        return f"Reserva {self.id}"

class Pedido(models.Model):
    ESTADOS = (
        ("Pendiente", "Pendiente"),
        ("Pagado", "Pagado"),
        ("Entregado", "Entregado"),
        ("Cancelado", "Cancelado"),
    )

    cliente = models.ForeignKey(Usuario, on_delete=models.DO_NOTHING, related_name="pedidos")
    fecha = models.DateTimeField(auto_now_add=True)
    total = models.IntegerField(default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="Pendiente")

    def __str__(self):
        return f"Pedido {self.id} - {self.cliente.nombre}"

class PedidoProducto(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="productos")
    producto = models.ForeignKey(Producto, on_delete=models.DO_NOTHING, related_name="pedidos_productos")
    cantidad = models.IntegerField(default=1)
    precio = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.producto.nombre} x{self.cantidad}"
