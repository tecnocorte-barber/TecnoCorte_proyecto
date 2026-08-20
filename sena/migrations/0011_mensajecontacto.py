from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sena", "0010_horariotrabajo_bloqueohorario")]

    operations = [
        migrations.CreateModel(
            name="MensajeContacto",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100)),
                ("email", models.EmailField(max_length=254)),
                ("asunto", models.CharField(max_length=150)),
                ("mensaje", models.TextField()),
                ("fecha", models.DateTimeField(auto_now_add=True)),
                ("leido", models.BooleanField(default=False)),
            ],
            options={"ordering": ["-fecha"]},
        ),
    ]
