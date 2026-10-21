from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('sena', '0034_restricciones_datos')]

    operations = [
        migrations.CreateModel(
            name='JWTRefreshToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jti_hash', models.CharField(max_length=64, unique=True)),
                ('expira', models.DateTimeField()),
                ('revocado', models.BooleanField(default=False)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('revocado_en', models.DateTimeField(blank=True, null=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='refresh_tokens', to='sena.usuario')),
            ],
            options={
                'indexes': [
                    models.Index(fields=['usuario', 'revocado'], name='sena_jwtref_usuario_e6f425_idx'),
                    models.Index(fields=['expira'], name='sena_jwtref_expira_deeef1_idx'),
                ],
            },
        ),
    ]
