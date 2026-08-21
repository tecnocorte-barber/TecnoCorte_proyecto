from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sena", "0019_proteger_relaciones")]

    operations = [
        migrations.AlterField(
            model_name="usuario",
            name="password",
            field=models.CharField(max_length=128),
        ),
    ]
