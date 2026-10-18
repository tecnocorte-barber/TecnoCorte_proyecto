"""Catálogo y validaciones de servicios de barbería."""

SERVICIOS = [
    {"nombre": "Corte de Cabello", "descripcion": "Lavado, corte preciso con tijera y máquina, peinado con productos premium.", "duracion": "45 Minutos", "minutos": 45, "precio": 40000},
    {"nombre": "Arreglo de Barba", "descripcion": "Toalla caliente, perfilado exacto, hidratación con aceites esenciales.", "duracion": "30 Minutos", "minutos": 30, "precio": 30000},
    {"nombre": "Combo Completo", "descripcion": "Corte de cabello + arreglo de barba + limpieza facial.", "duracion": "1 Hora 15 Min", "minutos": 75, "precio": 60000},
]

DURACIONES_SERVICIO = [15, 20, 30, 45, 60, 75, 90, 120]


def catalogo_servicios():
    """Combina servicios base con servicios propios aprobados."""
    from sena.models import Servicio

    lista, vistos = [], set()
    for item in SERVICIOS:
        vistos.add(item["nombre"])
        lista.append(item)
    for servicio in Servicio.objects.filter(activo=True).select_related("barbero"):
        if servicio.nombre in vistos:
            continue
        vistos.add(servicio.nombre)
        lista.append(servicio.a_dict())
    return lista


def servicio_valido(nombre):
    return bool(nombre) and nombre in {item["nombre"] for item in catalogo_servicios()}


def minutos_servicio(servicio):
    return next((item["minutos"] for item in catalogo_servicios() if item["nombre"] == servicio), 30)
