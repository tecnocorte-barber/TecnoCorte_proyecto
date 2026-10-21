"""Crea un backup comprimido de PostgreSQL y lo envía si cabe en el correo."""
import gzip
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from cryptography.fernet import Fernet


class Command(BaseCommand):
    help = "Genera un backup PostgreSQL .sql.gz, registra la ejecución y opcionalmente lo envía por correo."

    def add_arguments(self, parser):
        parser.add_argument("--sin-correo", action="store_true", help="Solo crea el archivo local.")
        parser.add_argument("--salida", default="backups", help="Directorio para guardar el backup.")

    def handle(self, *args, **options):
        salida = Path(options["salida"])
        salida.mkdir(parents=True, exist_ok=True)
        nombre = f"tecnocorte_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.sql.gz.enc"
        archivo = salida / nombre
        db = settings.DATABASES["default"]
        env = os.environ.copy()
        if db.get("PASSWORD"):
            env["PGPASSWORD"] = db["PASSWORD"]
        comando = ["pg_dump", "--dbname", db.get("NAME", ""), "--host", db.get("HOST", ""),
                   "--port", str(db.get("PORT", "5432")), "--username", db.get("USER", "")]
        inicio = datetime.now(timezone.utc).isoformat()
        try:
            with tempfile.TemporaryFile() as crudo:
                proceso = subprocess.run(comando, stdout=crudo, stderr=subprocess.PIPE, env=env, check=False)
                if proceso.returncode:
                    raise CommandError(proceso.stderr.decode(errors="replace")[-1000:])
                crudo.seek(0)
                comprimido = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
                with gzip.GzipFile(fileobj=comprimido, mode="wb") as gzip_file:
                    while bloque := crudo.read(1024 * 1024):
                        gzip_file.write(bloque)
                comprimido.seek(0)
                try:
                    clave = settings.BACKUP_ENCRYPTION_KEY.encode()
                    cifrador = Fernet(clave)
                except (ValueError, TypeError) as exc:
                    raise CommandError("BACKUP_ENCRYPTION_KEY no es una clave Fernet válida.") from exc
                archivo.write_bytes(cifrador.encrypt(comprimido.read()))
                comprimido.close()
            tamano = archivo.stat().st_size
            if tamano > settings.BACKUP_MAX_ATTACHMENT_BYTES and not options["sin_correo"]:
                raise CommandError(f"El backup ({tamano} bytes) supera el límite de adjuntos configurado.")
            if not options["sin_correo"]:
                correo = EmailMessage("Backup cifrado de TecnoCorte", "Backup PostgreSQL cifrado generado correctamente.",
                                      settings.DEFAULT_FROM_EMAIL, [settings.BACKUP_EMAIL])
                correo.attach_file(str(archivo))
                correo.send(fail_silently=False)
            self.stdout.write(self.style.SUCCESS(f"Backup creado: {archivo} ({tamano} bytes)"))
            self._registrar({"inicio": inicio, "fin": datetime.now(timezone.utc).isoformat(), "estado": "ok",
                             "archivo": str(archivo), "bytes": tamano, "correo": not options["sin_correo"]})
        except (OSError, subprocess.SubprocessError, CommandError) as exc:
            self._registrar({"inicio": inicio, "fin": datetime.now(timezone.utc).isoformat(), "estado": "error", "error": str(exc)})
            if archivo.exists():
                archivo.unlink()
            if isinstance(exc, CommandError):
                raise
            raise CommandError(str(exc)) from exc

    def _registrar(self, datos):
        ruta = Path(getattr(settings, "BASE_DIR", Path.cwd())) / "backups" / "backup.log"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open("a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(datos, ensure_ascii=False) + "\n")
