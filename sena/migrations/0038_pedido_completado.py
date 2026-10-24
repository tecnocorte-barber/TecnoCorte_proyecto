from django.db import migrations, models


def cerrar_pedidos_entregados_y_pagados(apps, schema_editor):
    Pedido = apps.get_model("sena", "Pedido")
    Pedido.objects.filter(estado="Entregado", pago_confirmado=True).update(
        estado="Completado"
    )


class Migration(migrations.Migration):
    dependencies = [("sena", "0037_registropendiente")]

    operations = [
        migrations.AlterField(
            model_name="pedido",
            name="estado",
            field=models.CharField(
                choices=[
                    ("Pendiente", "Pendiente"),
                    ("Listo", "Listo para recoger"),
                    ("Entregado", "Entregado"),
                    ("Completado", "Completado"),
                    ("Cancelado", "Cancelado"),
                ],
                default="Pendiente",
                max_length=20,
            ),
        ),
        migrations.RunPython(
            cerrar_pedidos_entregados_y_pagados,
            migrations.RunPython.noop,
        ),
    ]
