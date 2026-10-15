# Crea la fila única de configuración del sitio (pk=1) si no existe todavía.
from django.db import migrations


def crear_configuracion(apps, schema_editor):
    Configuracion = apps.get_model("sena", "Configuracion")
    Configuracion.objects.get_or_create(pk=1)


def borrar_configuracion(apps, schema_editor):
    Configuracion = apps.get_model("sena", "Configuracion")
    Configuracion.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("sena", "0024_configuracion_alter_producto_imagen"),
    ]

    operations = [
        migrations.RunPython(crear_configuracion, borrar_configuracion),
    ]
