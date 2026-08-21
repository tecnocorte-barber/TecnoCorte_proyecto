from django.db import migrations
from django.contrib.auth.hashers import make_password


def hash_existing_passwords(apps, schema_editor):
    Usuario = apps.get_model("sena", "Usuario")
    for usuario in Usuario.objects.all().iterator():
        if not usuario.password.startswith(("pbkdf2_", "argon2", "bcrypt", "scrypt")):
            usuario.password = make_password(usuario.password)
            usuario.save(update_fields=["password"])


class Migration(migrations.Migration):
    dependencies = [("sena", "0017_merge_20260820_1340")]

    operations = [migrations.RunPython(hash_existing_passwords, migrations.RunPython.noop)]
