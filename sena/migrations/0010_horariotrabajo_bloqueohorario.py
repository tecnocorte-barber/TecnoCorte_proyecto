from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sena", "0009_actualizar_roles_peluquero_a_barbero")]

    operations = [
        migrations.CreateModel(
            name="HorarioTrabajo",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dia_semana", models.PositiveSmallIntegerField(choices=[(0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"), (4, "Viernes"), (5, "Sábado"), (6, "Domingo")], unique=True)),
                ("activo", models.BooleanField(default=True)),
                ("hora_inicio", models.TimeField(default="09:00")),
                ("hora_fin", models.TimeField(default="18:00")),
            ],
        ),
        migrations.CreateModel(
            name="BloqueoHorario",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateField()),
                ("hora", models.TimeField(blank=True, null=True)),
                ("motivo", models.CharField(blank=True, max_length=150)),
            ],
            options={"ordering": ["fecha", "hora"]},
        ),
    ]
