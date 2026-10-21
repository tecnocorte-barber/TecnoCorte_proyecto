from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('sena', '0032_usuario_sesion_version_registroaccion')]

    operations = [
        migrations.AddField(
            model_name='usuario', name='email_verificado',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='usuario', name='codigo_verificacion_hash',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='usuario', name='codigo_verificacion_expira',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
