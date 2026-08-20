from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sena", "0011_mensajecontacto")]

    operations = [
        migrations.AlterField(
            model_name="reserva",
            name="estado",
            field=models.CharField(choices=[("Pendiente", "Pendiente"), ("Confirmada", "Confirmada"), ("Completada", "Completada"), ("Cancelada", "Cancelada")], default="Pendiente", max_length=20),
        ),
    ]
