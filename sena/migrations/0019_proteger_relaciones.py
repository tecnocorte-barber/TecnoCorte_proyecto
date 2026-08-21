from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sena", "0018_migrar_passwords")]

    operations = [
        migrations.AlterField(
            model_name="reserva",
            name="cliente",
            field=models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="reservas_cliente", to="sena.usuario"),
        ),
        migrations.AlterField(
            model_name="reserva",
            name="peluquero",
            field=models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="reservas_peluquero", to="sena.usuario"),
        ),
        migrations.AlterField(
            model_name="reserva",
            name="peluqueria",
            field=models.ForeignKey(on_delete=models.deletion.PROTECT, to="sena.peluqueria"),
        ),
        migrations.AlterField(
            model_name="pedido",
            name="cliente",
            field=models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="pedidos", to="sena.usuario"),
        ),
        migrations.AlterField(
            model_name="pedidoproducto",
            name="producto",
            field=models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="pedidos_productos", to="sena.producto"),
        ),
    ]
