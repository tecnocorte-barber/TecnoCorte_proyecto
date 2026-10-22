# TecnoCorte Mobile

Aplicación Flutter que consume la API REST del proyecto Django.

## Iniciar la API Django

Desde la raíz del repositorio:

```bash
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

## Ejecutar la app

Desde `mobile_app/`:

### Emulador Android

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api
```

### Celular físico en la misma red

Reemplaza `192.168.1.20` por la IP local del computador:

```bash
flutter run --dart-define=API_BASE_URL=http://192.168.1.20:8000/api
```

El firewall debe permitir el puerto `8000`. La IP también debe estar incluida
en `DJANGO_ALLOWED_HOSTS` si Django la rechaza.

### Producción

Usa siempre HTTPS:

```bash
flutter build apk --dart-define=API_BASE_URL=https://tu-dominio.com/api
```

La app registra o autentica al cliente mediante JWT y luego consulta servicios,
sedes, barberos y reservas usando el access token. Los tokens se guardan
localmente para mantener la sesión.

No se deben versionar `android/local.properties`, `.dart_tool/`, `build/` ni
credenciales. La URL de la API se configura con `--dart-define`.
