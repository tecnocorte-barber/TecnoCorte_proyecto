from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("sena", "0038_pedido_completado")]
    operations = [migrations.AlterField(
        model_name="usuario", name="rol",
        field=models.CharField(max_length=15, default="Cliente", choices=[
            ("SuperAdmin", "SUPER ADMINISTRADOR"), ("Admin", "ADMINISTRADOR"),
            ("Barbero", "BARBERO"), ("Cliente", "CLIENTE")]),
    )]
