from django.db import migrations
from django.db.models import Exists, OuterRef


def marcar_servicios_retirados(apps, schema_editor):
    SolicitudServicio = apps.get_model("sena", "SolicitudServicio")
    Servicio = apps.get_model("sena", "Servicio")
    servicios_retirados = Servicio.objects.filter(
        barbero_id=OuterRef("barbero_id"),
        nombre__iexact=OuterRef("nombre"),
        activo=False,
    )
    SolicitudServicio.objects.filter(estado="aprobada").annotate(
        servicio_retirado=Exists(servicios_retirados)
    ).filter(servicio_retirado=True).update(estado="eliminada")


class Migration(migrations.Migration):

    dependencies = [
        ("sena", "0040_solicitudservicio_estado_eliminada"),
    ]

    operations = [
        migrations.RunPython(
            marcar_servicios_retirados,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
