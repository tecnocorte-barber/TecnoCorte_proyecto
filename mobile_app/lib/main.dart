import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

const accent = Color(0xFFD5A85B);
const dark = Color(0xFF11100F);
const apiBase = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://127.0.0.1:8000/api',
);

void main() => runApp(const TecnoCorteApp());

class Api {
  final prefs = SharedPreferences.getInstance();
  Future<Map<String, String>> headers() async {
    final p = await prefs;
    final token = p.getString('access');
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  Future<dynamic> get(String path) async => _decode(
    await http.get(Uri.parse('$apiBase$path'), headers: await headers()),
  );
  Future<dynamic> post(String path, Map<String, dynamic> body) async => _decode(
    await http.post(
      Uri.parse('$apiBase$path'),
      headers: await headers(),
      body: jsonEncode(body),
    ),
  );
  dynamic _decode(http.Response r) {
    final data = r.body.isEmpty ? {} : jsonDecode(r.body);
    if (r.statusCode >= 400) throw Exception(_message(data));
    return data;
  }

  String _message(dynamic d) => d is Map
      ? (d['detail'] ?? d.values.first).toString()
      : 'Ocurrió un error.';
}

class TecnoCorteApp extends StatelessWidget {
  const TecnoCorteApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'TecnoCorte',
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: dark,
      colorScheme: ColorScheme.fromSeed(
        seedColor: accent,
        brightness: Brightness.dark,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFF201E1B),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide.none,
        ),
      ),
      cardTheme: const CardThemeData(
        color: Color(0xFF201E1B),
        margin: EdgeInsets.zero,
      ),
      fontFamily: 'sans-serif',
      appBarTheme: const AppBarTheme(
        backgroundColor: dark,
        elevation: 0,
        centerTitle: false,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: const Color(0xFF181614),
        indicatorColor: accent.withValues(alpha: .22),
        labelTextStyle: WidgetStatePropertyAll(
          TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
        ),
      ),
    ),
    home: const Gate(),
  );
}

/// Ancho completo en celulares y ancho limitado en tablets/escritorio.
class ResponsiveBody extends StatelessWidget {
  final Widget child;
  final double maxWidth;

  const ResponsiveBody({super.key, required this.child, this.maxWidth = 720});

  @override
  Widget build(BuildContext context) => Center(
    child: ConstrainedBox(
      constraints: BoxConstraints(maxWidth: maxWidth),
      child: child,
    ),
  );
}

class Gate extends StatefulWidget {
  const Gate({super.key});
  @override
  State<Gate> createState() => _GateState();
}

class _GateState extends State<Gate> {
  @override
  Widget build(BuildContext context) => FutureBuilder(
    future: SharedPreferences.getInstance(),
    builder: (_, s) {
      if (!s.hasData) {
        return const Scaffold(
          body: Center(child: CircularProgressIndicator(color: accent)),
        );
      }
      return s.data!.getString('access') == null
          ? const AuthPage()
          : const HomePage();
    },
  );
}

class AuthPage extends StatefulWidget {
  const AuthPage({super.key});
  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> {
  bool register = false, busy = false;
  final form = GlobalKey<FormState>();
  final name = TextEditingController(),
      last = TextEditingController(),
      phone = TextEditingController(),
      email = TextEditingController(),
      pass = TextEditingController();
  final api = Api();
  Future<void> submit() async {
    if (!form.currentState!.validate()) return;
    setState(() => busy = true);
    try {
      final data = register
          ? await api.post('/auth/register/', {
              'nombre': name.text,
              'apellido': last.text,
              'telefono': phone.text,
              'email': email.text,
              'password': pass.text,
            })
          : await api.post('/auth/token/', {
              'email': email.text,
              'password': pass.text,
            });
      final p = await api.prefs;
      await p.setString('access', data['access']);
      await p.setString('refresh', data['refresh'] ?? '');
      if (mounted) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const HomePage()),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  String? req(String? v) =>
      (v == null || v.trim().isEmpty) ? 'Campo obligatorio' : null;
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(28),
            child: Form(
              key: form,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'TC',
                      style: TextStyle(
                        color: accent,
                        fontSize: 48,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      register ? 'Crea tu cuenta' : 'Bienvenido a TecnoCorte',
                      style: const TextStyle(
                        fontSize: 27,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      register
                          ? 'Reserva tu próximo corte en pocos pasos.'
                          : 'Tu estilo comienza aquí.',
                      style: const TextStyle(color: Colors.white60),
                    ),
                    const SizedBox(height: 30),
                    if (register) ...[
                      field(name, 'Nombre', req),
                      const SizedBox(height: 14),
                      field(last, 'Apellido', req),
                      const SizedBox(height: 14),
                      field(phone, 'Teléfono (opcional)', null),
                      const SizedBox(height: 14),
                    ],
                    field(
                      email,
                      'Correo electrónico',
                      (v) =>
                          req(v) ??
                          (v!.contains('@') ? null : 'Correo no válido'),
                    ),
                    const SizedBox(height: 14),
                    field(pass, 'Contraseña', req, obscure: true),
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      height: 52,
                      child: FilledButton(
                        onPressed: busy ? null : submit,
                        child: busy
                            ? const CircularProgressIndicator()
                            : Text(register ? 'REGISTRARME' : 'INICIAR SESIÓN'),
                      ),
                    ),
                    const SizedBox(height: 18),
                    Center(
                      child: TextButton(
                        onPressed: () => setState(() => register = !register),
                        child: Text(
                          register ? 'Ya tengo una cuenta' : 'Crear una cuenta',
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget field(
    TextEditingController c,
    String label,
    String? Function(String?)? validator, {
    bool obscure = false,
  }) => TextFormField(
    controller: c,
    validator: validator,
    obscureText: obscure,
    decoration: InputDecoration(labelText: label),
  );
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final api = Api();
  int tab = 0;
  late Future<List<dynamic>> services, shops, appointments;
  @override
  void initState() {
    super.initState();
    reload();
  }

  void reload() {
    services = api.get('/servicios/').then((x) => x as List);
    shops = api.get('/peluquerias/').then((x) => x['results'] ?? x as List);
    appointments = api.get('/reservas/').then((x) => x['results'] ?? x as List);
  }

  Future<void> logout() async {
    final p = await api.prefs;
    await p.clear();
      if (mounted) {
        Navigator.pushAndRemoveUntil(
          context,
          MaterialPageRoute(builder: (_) => const AuthPage()),
          (_) => false,
        );
      }
  }

  @override
  Widget build(BuildContext context) {
    final pages = [_home(), _appointments(), _profile()];
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: const [
            Text(
              'TC',
              style: TextStyle(
                color: accent,
                fontWeight: FontWeight.w900,
                letterSpacing: 1.5,
              ),
            ),
            SizedBox(width: 10),
            Text('TecnoCorte', style: TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
        actions: [
          IconButton(onPressed: logout, icon: const Icon(Icons.logout)),
        ],
      ),
      body: ResponsiveBody(child: pages[tab]),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (v) => setState(() => tab = v),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            label: 'Inicio',
          ),
          NavigationDestination(
            icon: Icon(Icons.calendar_month_outlined),
            label: 'Mis citas',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            label: 'Perfil',
          ),
        ],
      ),
    );
  }

  Widget _home() => RefreshIndicator(
    onRefresh: () async {
      setState(reload);
    },
    child: ListView(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 30),
      children: [
        Container(
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF3A2B1D), Color(0xFF201E1B)],
            ),
            borderRadius: BorderRadius.circular(24),
          ),
          child: const Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.auto_awesome, color: accent, size: 25),
              SizedBox(height: 18),
              Text(
                'Tu mejor versión\nempieza en la silla.',
                style: TextStyle(
                  fontSize: 25,
                  height: 1.1,
                  fontWeight: FontWeight.w800,
                ),
              ),
              SizedBox(height: 8),
              Text(
                'Estilo, cuidado y precisión en cada visita.',
                style: TextStyle(color: Colors.white70),
              ),
            ],
          ),
        ),
        const SizedBox(height: 26),
        const Text(
          'Tu próximo look',
          style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 5),
        const Text(
          'Servicios pensados para ti',
          style: TextStyle(color: Colors.white60),
        ),
        const SizedBox(height: 22),
        FutureBuilder<List<dynamic>>(
          future: services,
          builder: (_, s) => s.hasError
              ? _errorCard('No pudimos cargar los servicios.')
              : s.hasData
              ? Column(children: s.data!.map((x) => _service(x)).toList())
              : const Center(child: CircularProgressIndicator(color: accent)),
        ),
        const SizedBox(height: 24),
        const Text(
          'Nuestras sedes',
          style: TextStyle(fontSize: 21, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 12),
        FutureBuilder<List<dynamic>>(
          future: shops,
          builder: (_, s) => s.hasData
              ? Column(
                  children: s.data!
                      .map(
                        (x) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const CircleAvatar(
                            backgroundColor: accent,
                            child: Icon(Icons.store, color: dark),
                          ),
                          title: Text(x['nombre'] ?? ''),
                          subtitle: Text(
                            x['ubicacion'] ?? 'Ubicación no registrada',
                          ),
                        ),
                      )
                      .toList(),
                )
              : s.hasError
              ? _errorCard('No pudimos cargar las sedes.')
              : const SizedBox(),
        ),
      ],
    ),
  );
  Widget _service(dynamic x) => Card(
    margin: const EdgeInsets.only(bottom: 12),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            width: 50,
            height: 50,
            decoration: BoxDecoration(
               color: accent.withValues(alpha: .15),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Icon(Icons.content_cut, color: accent),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  x['nombre'],
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  x['descripcion'] ?? '',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white60),
                ),
                const SizedBox(height: 6),
                Text(
                  '\$${NumberFormat('#,###', 'es_CO').format(x['precio'] ?? 0)}  ·  ${x['duracion']}',
                  style: const TextStyle(
                    color: accent,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          IconButton(
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => BookingPage(service: x)),
            ).then((_) => setState(reload)),
            icon: const Icon(Icons.arrow_forward, color: accent),
          ),
        ],
      ),
    ),
  );

  Widget _errorCard(String message) => Card(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Row(
        children: [
          const Icon(Icons.wifi_off, color: accent),
          const SizedBox(width: 12),
          Expanded(
            child: Text(message, style: const TextStyle(color: Colors.white70)),
          ),
        ],
      ),
    ),
  );
  Widget _appointments() => FutureBuilder<List<dynamic>>(
    future: appointments,
    builder: (_, s) {
      if (!s.hasData) {
        return const Center(child: CircularProgressIndicator(color: accent));
      }
      if (s.hasError) {
        return const Center(child: Text('No pudimos cargar tus citas.'));
      }
      if (s.data!.isEmpty) {
        return const Center(child: Text('Aún no tienes citas.'));
      }
      return ListView(
        padding: const EdgeInsets.all(20),
        children: s.data!
            .map(
              (x) => Card(
                child: ListTile(
                  leading: const Icon(Icons.event, color: accent),
                  title: Text(x['servicio'] ?? ''),
                  subtitle: Text(
                    '${x['fecha']} · ${x['hora']}\n${x['peluqueria_nombre'] ?? ''}',
                  ),
                  isThreeLine: true,
                  trailing: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 90),
                    child: Text(
                      x['estado'] ?? '',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.end,
                    ),
                  ),
                ),
              ),
            )
            .toList(),
      );
    },
  );
  Widget _profile() => ListView(
    padding: const EdgeInsets.all(20),
    children: [
      const CircleAvatar(
        radius: 38,
        backgroundColor: accent,
        child: Icon(Icons.person, color: dark, size: 38),
      ),
      const SizedBox(height: 14),
      const Center(
        child: Text(
          'Tu cuenta TecnoCorte',
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
        ),
      ),
      const SizedBox(height: 28),
      Card(
        child: ListTile(
          leading: const Icon(Icons.verified_user, color: accent),
          title: const Text('Cuenta activa'),
          subtitle: const Text('Gestiona tus citas desde cualquier lugar.'),
        ),
      ),
      const SizedBox(height: 12),
      OutlinedButton.icon(
        onPressed: logout,
        icon: const Icon(Icons.logout),
        label: const Text('Cerrar sesión'),
      ),
    ],
  );
}

class BookingPage extends StatefulWidget {
  final dynamic service;
  const BookingPage({super.key, required this.service});
  @override
  State<BookingPage> createState() => _BookingPageState();
}

class _BookingPageState extends State<BookingPage> {
  final api = Api();
  DateTime? date;
  TimeOfDay? time;
  dynamic shop, barber;
  List<dynamic> shops = [], barbers = [];
  List<dynamic> services = [];
  String? serviceName;
  String? serviceError;
  bool loadingServices = false;
  bool busy = false;
  int _servicesRequest = 0;

  dynamic get selectedService => services.firstWhere(
    (item) => item['nombre'] == serviceName,
    orElse: () => widget.service,
  );

  @override
  void initState() {
    super.initState();
    services = [widget.service];
    serviceName = widget.service['nombre'] as String?;
    load();
  }

  Future<void> load() async {
    try {
      final a = await api.get('/peluquerias/');
      final b = await api.get('/barberos/');
      if (mounted) {
        setState(() {
          shops = a['results'] ?? a;
          barbers = b;
        });
      }
    } catch (_) {}
  }

  Future<void> loadServicesForBarber(dynamic selectedBarber) async {
    final requestId = ++_servicesRequest;
    if (selectedBarber == null) {
      setState(() {
        services = [widget.service];
        serviceName = widget.service['nombre'] as String?;
        serviceError = null;
        loadingServices = false;
      });
      return;
    }
    setState(() {
      loadingServices = true;
      serviceError = null;
    });
    try {
      final result = await api.get('/servicios/?barbero=${selectedBarber['id']}');
      final available = result as List<dynamic>;
      if (!mounted || requestId != _servicesRequest) return;
      setState(() {
        services = available;
        if (!available.any((item) => item['nombre'] == serviceName)) {
          serviceName = null;
        }
        loadingServices = false;
      });
    } catch (_) {
      if (!mounted || requestId != _servicesRequest) return;
      setState(() {
        serviceError = 'No pudimos cargar los servicios de este barbero.';
        loadingServices = false;
      });
    }
  }

  Future<void> send() async {
    if (date == null || shop == null || barber == null || serviceName == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Elige sede, barbero, servicio y fecha.')),
      );
      return;
    }
    setState(() => busy = true);
    try {
      await api.post('/reservas/', {
        'peluqueria': shop['id'],
        'peluquero': barber['id'],
        'fecha': DateFormat('yyyy-MM-dd').format(date!),
        'hora': time == null
            ? '10:00'
            : '${time!.hour.toString().padLeft(2, '0')}:${time!.minute.toString().padLeft(2, '0')}',
        'servicio': serviceName,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('¡Cita reservada correctamente!')),
        );
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Reservar cita')),
    body: ResponsiveBody(
      maxWidth: 600,
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            selectedService['nombre'],
            style: const TextStyle(fontSize: 27, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text(
            selectedService['descripcion'] ?? '',
            style: const TextStyle(color: Colors.white60),
          ),
          const SizedBox(height: 28),
          const Text('Sede', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          DropdownButtonFormField<dynamic>(
             initialValue: shop,
            items: shops
                .map(
                  (x) => DropdownMenuItem(value: x, child: Text(x['nombre'])),
                )
                .toList(),
            onChanged: (v) => setState(() {
              _servicesRequest++;
              shop = v;
              barber = null;
              services = [widget.service];
              serviceName = widget.service['nombre'] as String?;
              serviceError = null;
              loadingServices = false;
            }),
            decoration: const InputDecoration(hintText: 'Selecciona una sede'),
          ),
          const SizedBox(height: 18),
          const Text('Barbero', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          DropdownButtonFormField<dynamic>(
             initialValue: barber,
            items: barbers
                .where((x) => shop == null || x['peluqueria'] == shop['id'])
                .map(
                  (x) => DropdownMenuItem(value: x, child: Text(x['nombre'])),
                )
                .toList(),
            onChanged: (v) {
              setState(() {
                barber = v;
                services = [widget.service];
                serviceName = widget.service['nombre'] as String?;
              });
              loadServicesForBarber(v);
            },
            decoration: const InputDecoration(
              hintText: 'Selecciona un barbero',
            ),
          ),
          const SizedBox(height: 18),
          const Text('Servicio', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            initialValue: services.any((item) => item['nombre'] == serviceName)
                ? serviceName
                : null,
            items: services
                .map((item) => DropdownMenuItem<String>(
                      value: item['nombre'] as String,
                      child: Text(item['nombre'] as String),
                    ))
                .toList(),
            onChanged: loadingServices
                ? null
                : (value) => setState(() => serviceName = value),
            decoration: InputDecoration(
              hintText: loadingServices
                  ? 'Cargando servicios...'
                  : 'Selecciona un servicio',
            ),
          ),
          if (serviceError != null) ...[
            const SizedBox(height: 6),
            Text(serviceError!, style: const TextStyle(color: Colors.redAccent)),
          ],
          const SizedBox(height: 18),
          const Text('Fecha', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () async {
              final d = await showDatePicker(
                context: context,
                firstDate: DateTime.now(),
                lastDate: DateTime.now().add(const Duration(days: 90)),
                initialDate: DateTime.now().add(const Duration(days: 1)),
              );
              if (d != null) setState(() => date = d);
            },
            icon: const Icon(Icons.calendar_today),
            label: Text(
              date == null
                  ? 'Elegir fecha'
                  : DateFormat('EEEE d MMMM', 'es_CO').format(date!),
            ),
          ),
          const SizedBox(height: 18),
          const Text('Hora', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () async {
              final picked = await showTimePicker(
                context: context,
                initialTime: const TimeOfDay(hour: 10, minute: 0),
              );
              if (picked != null) setState(() => time = picked);
            },
            icon: const Icon(Icons.schedule),
            label: Text(time == null ? 'Elegir hora' : time!.format(context)),
          ),
          const SizedBox(height: 30),
          SizedBox(
            height: 52,
            child: FilledButton(
              onPressed: busy ? null : send,
              child: busy
                  ? const CircularProgressIndicator()
                  : const Text('CONFIRMAR RESERVA'),
            ),
          ),
        ],
      ),
    ),
  );
}
