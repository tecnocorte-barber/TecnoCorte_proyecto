"""Restaura un backup PostgreSQL cifrado, exigiendo confirmación explícita."""
import os
import subprocess
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restaura un archivo .sql.gz.enc de PostgreSQL; requiere --confirmar."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=Path)
        parser.add_argument("--confirmar", action="store_true", help="Confirma que se reemplazará la base de datos.")

    def handle(self, *args, **options):
        archivo = options["archivo"]
        if not options["confirmar"]:
            raise CommandError("La restauración es destructiva. Repite el comando con --confirmar.")
        if not archivo.is_file() or archivo.suffix != ".enc":
            raise CommandError("Indica un archivo de backup .sql.gz.enc existente.")
        try:
            datos = Fernet(settings.BACKUP_ENCRYPTION_KEY.encode()).decrypt(archivo.read_bytes())
        except Exception as exc:
            raise CommandError("No se pudo descifrar el backup. Revisa BACKUP_ENCRYPTION_KEY.") from exc

        db = settings.DATABASES["default"]
        entorno = os.environ.copy()
        if db.get("PASSWORD"):
            entorno["PGPASSWORD"] = db["PASSWORD"]
        comando = ["psql", "--dbname", db.get("NAME", ""), "--host", db.get("HOST", ""),
                   "--port", str(db.get("PORT", "5432")), "--username", db.get("USER", "")]
        try:
            with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as temporal:
                temporal.write(datos)
                temporal.flush()
                ruta = temporal.name
            # psql no descomprime gzip: se descomprime mediante gzip antes de restaurar.
            import gzip
            sql = gzip.open(ruta, "rb").read()
            proceso = subprocess.run(comando, input=sql, env=entorno, capture_output=True, check=False)
            if proceso.returncode:
                raise CommandError(proceso.stderr.decode(errors="replace")[-2000:])
        except OSError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            if "ruta" in locals():
                Path(ruta).unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS("Backup restaurado correctamente."))
