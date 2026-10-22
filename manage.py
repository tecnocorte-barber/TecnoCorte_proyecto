#!/usr/bin/env python
# Script principal para ejecutar los comandos de administración de Django
# (runserver, migrate, createsuperuser, etc.) en el proyecto TecnoCorte
import os, sys

# Función principal: usa SQLite para que los comandos locales funcionen sin
# depender de una base de datos PostgreSQL remota. En producción se puede
# seleccionar explícitamente `tecnocorte.settings`.
def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tecnocorte.settings_local')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)

# Punto de entrada: ejecuta main() solo cuando el archivo se corre directamente
if __name__ == '__main__':
    main()
