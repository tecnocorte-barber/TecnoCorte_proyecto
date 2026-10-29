"""Catálogo y validaciones de servicios de barbería."""

SERVICIOS = [
    {"nombre": "Corte de Cabello", "descripcion": "Lavado, corte preciso con tijera y máquina, peinado con productos premium.", "duracion": "45 Minutos", "minutos": 45, "precio": 17000},
    {"nombre": "Arreglo de Barba", "descripcion": "Toalla caliente, perfilado exacto, hidratación con aceites esenciales.", "duracion": "30 Minutos", "minutos": 30, "precio": 12000},
    {"nombre": "Combo Completo", "descripcion": "Corte de cabello + arreglo de barba + limpieza facial.", "duracion": "1 Hora 15 Min", "minutos": 75, "precio": 25000},
]

DURACIONES_SERVICIO = [15, 20, 30, 45, 60, 75, 90, 120]


def catalogo_servicios(barbero_id=None, incluir_personalizados=False):
    """Devuelve servicios base y, cuando se solicita, los propios de un barbero."""
    from sena.models import Servicio

    lista, vistos = [], set()
    for item in SERVICIOS:
        vistos.add(item["nombre"].casefold())
        lista.append(item)
    if barbero_id is None and not incluir_personalizados:
        return lista
    servicios = Servicio.objects.filter(activo=True).select_related(
        "barbero", "barbero__peluqueria"
    )
    if barbero_id is not None:
        servicios = servicios.filter(barbero_id=barbero_id)
    for servicio in servicios:
        if servicio.nombre.casefold() in vistos:
            continue
        lista.append({
            **servicio.a_dict(),
            "barbero_id": servicio.barbero_id,
            "peluqueria_id": servicio.barbero.peluqueria_id,
        })
    return lista


def servicio_valido(nombre, barbero_id=None):
    return bool(nombre) and nombre in {
        item["nombre"] for item in catalogo_servicios(barbero_id=barbero_id)
    }


def minutos_servicio(servicio, barbero_id=None):
    return next(
        (
            item["minutos"]
            for item in catalogo_servicios(barbero_id=barbero_id)
            if item["nombre"] == servicio
        ),
        30,
    )
