part of 'main.dart';

const ink = Color(0xFF163D36), green = Color(0xFF19745D), lime = Color(0xFFDDF290), paper = Color(0xFFF5F7F3), muted = Color(0xFF70817A), line = Color(0xFFE3E9E1);
Map<String, dynamic> asMap(dynamic value) => Map<String, dynamic>.from(value as Map);
List<Map<String, dynamic>> asRows(dynamic value) => (value as List).map(asMap).toList();
String human(dynamic value) => (value ?? '—').toString().replaceAll('_', ' ');
String numText(dynamic value, [int places = 2]) => value is num ? value.toStringAsFixed(places) : '—';
String dateText(dynamic value) { final d = DateTime.tryParse('$value'); return d == null ? '—' : '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}'; }

ThemeData appTheme() => ThemeData(
  useMaterial3: true, scaffoldBackgroundColor: paper,
  colorScheme: ColorScheme.fromSeed(seedColor: green, primary: green, secondary: ink, surface: Colors.white),
  fontFamily: 'Roboto',
  textTheme: const TextTheme(headlineLarge: TextStyle(fontSize: 34, fontWeight: FontWeight.w800, color: ink, letterSpacing: -1), headlineMedium: TextStyle(fontSize: 27, fontWeight: FontWeight.w800, color: ink, letterSpacing: -.7), titleLarge: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: ink), titleMedium: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: ink), bodyMedium: TextStyle(fontSize: 14, color: ink, height: 1.5)),
  cardTheme: CardThemeData(color: Colors.white, elevation: 0, margin: EdgeInsets.zero, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20), side: const BorderSide(color: line))),
  inputDecorationTheme: InputDecorationTheme(filled: true, fillColor: const Color(0xFFFAFBF9), contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 17), border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: line)), enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: line))),
  filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)))),
  outlinedButtonTheme: OutlinedButtonThemeData(style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 17), side: const BorderSide(color: line), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)))),
  appBarTheme: const AppBarTheme(backgroundColor: paper, foregroundColor: ink, elevation: 0, centerTitle: false),
  dividerTheme: const DividerThemeData(color: line),
);

class ApiException implements Exception { const ApiException(this.status, this.message); final int status; final String message; @override String toString() => message; }
class NetworkException implements Exception { @override String toString() => 'Cannot reach the API. Check your connection and API_URL, then retry.'; }
class ApiClient {
  ApiClient({String? baseUrl, http.Client? client}) : baseUrl = baseUrl ?? const String.fromEnvironment('API_URL', defaultValue: 'http://localhost:8000'), client = client ?? http.Client();
  String baseUrl;
  final http.Client client;
  final storage = const FlutterSecureStorage(aOptions: AndroidOptions(encryptedSharedPreferences: true));
  String? token;
  SharedPreferences? prefs;
  bool offline = false;
  VoidCallback? onUnauthorized;
  Future<void> restore() async {
    prefs = await SharedPreferences.getInstance();
    final saved = prefs?.getString('packwise_api_url');
    if (saved != null && saved.trim().isNotEmpty) { baseUrl = saved.trim(); }
    token = await storage.read(key: 'packwise_session');
  }
  Future<void> setBaseUrl(String url) async {
    var clean = url.trim();
    if (clean.endsWith('/')) clean = clean.substring(0, clean.length - 1);
    if (!clean.startsWith('http://') && !clean.startsWith('https://')) clean = 'http://$clean';
    baseUrl = clean;
    await prefs?.setString('packwise_api_url', clean);
  }
  Future<Map<String, dynamic>> testConnection([String? targetUrl]) async {
    final root = targetUrl ?? baseUrl;
    var clean = root.trim();
    if (clean.endsWith('/')) clean = clean.substring(0, clean.length - 1);
    if (!clean.startsWith('http://') && !clean.startsWith('https://')) clean = 'http://$clean';
    final sw = Stopwatch()..start();
    try {
      final res = await client.get(Uri.parse('$clean/api/health')).timeout(const Duration(seconds: 6));
      sw.stop();
      if (res.statusCode >= 200 && res.statusCode < 300) {
        return {'ok': true, 'ms': sw.elapsedMilliseconds, 'data': jsonDecode(res.body)};
      }
      return {'ok': false, 'ms': sw.elapsedMilliseconds, 'error': 'Status ${res.statusCode}: ${res.body}'};
    } catch (e) {
      sw.stop();
      return {'ok': false, 'ms': sw.elapsedMilliseconds, 'error': e.toString()};
    }
  }
  Map<String, String> get headers => {'Content-Type': 'application/json', if (token != null) 'Authorization': 'Bearer $token'};
  dynamic decode(http.Response response, {bool binary = false}) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      dynamic data;
      try { data = jsonDecode(response.body); } catch (_) { data = null; }
      dynamic detail = data is Map ? data['detail'] : null;
      final message = detail is List ? detail.map((e) => '${(e['loc'] as List).skip(1).join('.')}: ${e['msg']}').join('\n') : detail is Map ? jsonEncode(detail) : detail?.toString() ?? 'Request failed (${response.statusCode})';
      if (response.statusCode == 401 && token != null && message != 'Current password is incorrect') { token = null; unawaited(storage.delete(key: 'packwise_session')); onUnauthorized?.call(); }
      throw ApiException(response.statusCode, message);
    }
    if (binary) return response.bodyBytes;
    return response.body.isEmpty ? null : jsonDecode(response.body);
  }
  Future<dynamic> request(String method, String path, [Object? body]) async {
    if (offline) throw NetworkException();
    final request = http.Request(method, Uri.parse('$baseUrl$path'))..headers.addAll(headers);
    if (body != null) request.body = jsonEncode(body);
    try { return decode(await http.Response.fromStream(await client.send(request).timeout(const Duration(seconds: 35)))); }
    on TimeoutException { throw NetworkException(); } on http.ClientException { throw NetworkException(); }
  }
  Future<dynamic> get(String path) => request('GET', path);
  Future<dynamic> post(String path, [Object? body]) => request('POST', path, body);
  Future<dynamic> patch(String path, Object body) => request('PATCH', path, body);
  Future<dynamic> delete(String path) => request('DELETE', path);
  Future<Map<String, dynamic>> authenticate(String path, Map<String, dynamic> body) async {
    offline = false;
    final data = asMap(await post(path, body)); await acceptSession(data); return asMap(data['user']);
  }
  Future<void> acceptSession(Map<String, dynamic> data) async { token = data['access_token'] as String; await storage.write(key: 'packwise_session', value: token); }
  Future<void> logout() async {
    try { if (!offline) await post('/api/auth/logout'); } catch (_) { /* Local session is always removed; server token expires. */ }
    token = null; offline = false;
    await storage.delete(key: 'packwise_session');
    for (final key in prefs?.getKeys().toList() ?? <String>[]) { if (key.startsWith('offline_') || key == 'last_user') await prefs?.remove(key); }
  }
  Future<dynamic> upload(String path, Uint8List bytes, String filename, {Map<String, String> fields = const {}}) async {
    if (offline) throw NetworkException();
    final req = http.MultipartRequest('POST', Uri.parse('$baseUrl$path'))..headers.addAll({if (token != null) 'Authorization': 'Bearer $token'})..fields.addAll(fields)..files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
    try { return decode(await http.Response.fromStream(await client.send(req).timeout(const Duration(seconds: 60)))); }
    on TimeoutException { throw NetworkException(); } on http.ClientException { throw NetworkException(); }
  }
  Future<Uint8List> bytes(String path) async {
    if (offline) throw NetworkException();
    try { return decode(await client.get(Uri.parse('$baseUrl$path'), headers: headers).timeout(const Duration(seconds: 35)), binary: true) as Uint8List; }
    on TimeoutException { throw NetworkException(); } on http.ClientException { throw NetworkException(); }
  }
  Future<String?> download(String path, String name, String ext) async {
    final value = await bytes(path);
    return FileSaver.instance.saveFile(name: name, bytes: value, ext: ext, mimeType: ext == 'pdf' ? MimeType.pdf : MimeType.csv);
  }
}

Future<PlatformFile?> pick(String ext) async { final result = await FilePicker.platform.pickFiles(type: FileType.custom, allowedExtensions: [ext], withData: true); if (result == null) return null; final file = result.files.single; if (file.size > 5 * 1024 * 1024) throw const ApiException(413, 'Choose a file smaller than 5 MB.'); return file; }
void toast(BuildContext context, String message) { if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message), behavior: SnackBarBehavior.floating)); }
Future<void> action(BuildContext context, Future<void> Function() work) async { try { await work(); } catch (e) { if (context.mounted) toast(context, e.toString()); } }
Future<void> showData(BuildContext context, String title, dynamic data) => showDialog<void>(context: context, builder: (context) => AlertDialog(title: Text(title), content: SizedBox(width: 650, child: SingleChildScrollView(child: DataView(data: data))), actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))]));

class Panel extends StatelessWidget { const Panel({super.key, required this.child, this.padding = 22, this.color}); final Widget child; final double padding; final Color? color; @override Widget build(BuildContext context) => Card(color: color, child: Padding(padding: EdgeInsets.all(padding), child: child)); }
class Pill extends StatelessWidget { const Pill(this.label, {super.key, this.warning = false}); final String label; final bool warning; @override Widget build(BuildContext context) => Container(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6), decoration: BoxDecoration(color: warning ? const Color(0xFFFFEBD6) : const Color(0xFFEBF3DF), borderRadius: BorderRadius.circular(8)), child: Text(human(label), style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: warning ? const Color(0xFF9E6228) : green))); }
class Heading extends StatelessWidget { const Heading(this.title, {super.key, this.subtitle, this.action}); final String title; final String? subtitle; final Widget? action; @override Widget build(BuildContext context) => Padding(padding: const EdgeInsets.only(bottom: 24), child: Wrap(alignment: WrapAlignment.spaceBetween, crossAxisAlignment: WrapCrossAlignment.center, spacing: 20, runSpacing: 14, children: [Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: Theme.of(context).textTheme.headlineMedium), if (subtitle != null) ...[const SizedBox(height: 6), Text(subtitle!, style: const TextStyle(color: muted))]]), if (action != null) action!])); }
class PageBody extends StatelessWidget { const PageBody({super.key, required this.children}); final List<Widget> children; @override Widget build(BuildContext context) => SingleChildScrollView(padding: EdgeInsets.all(MediaQuery.sizeOf(context).width < 700 ? 18 : 32), child: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 1400), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children)))); }
class Empty extends StatelessWidget { const Empty(this.title, this.message, {super.key, this.icon = Icons.inbox_outlined, this.action}); final String title, message; final IconData icon; final Widget? action; @override Widget build(BuildContext context) => Panel(child: Center(child: Padding(padding: const EdgeInsets.all(22), child: Column(children: [Icon(icon, size: 42, color: green), const SizedBox(height: 16), Text(title, style: Theme.of(context).textTheme.titleLarge), const SizedBox(height: 8), Text(message, textAlign: TextAlign.center, style: const TextStyle(color: muted)), if (action != null) ...[const SizedBox(height: 20), action!]])))); }
class LoadView extends StatelessWidget { const LoadView({super.key, required this.future, required this.builder, required this.retry}); final Future<dynamic> future; final Widget Function(dynamic) builder; final VoidCallback retry; @override Widget build(BuildContext context) => FutureBuilder<dynamic>(future: future, builder: (context, snap) { if (snap.connectionState != ConnectionState.done) return const Center(child: Padding(padding: EdgeInsets.all(50), child: CircularProgressIndicator())); if (snap.hasError) return Empty('Could not load this workspace', snap.error.toString(), icon: Icons.wifi_off_rounded, action: OutlinedButton(onPressed: retry, child: const Text('Try again'))); return builder(snap.data); }); }
class DataView extends StatelessWidget { const DataView({super.key, required this.data}); final dynamic data; @override Widget build(BuildContext context) { if (data == null) return const Text('Not available'); if (data is Map) return Column(crossAxisAlignment: CrossAxisAlignment.start, children: (data as Map).entries.map<Widget>((e) => Padding(padding: const EdgeInsets.only(bottom: 12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(human(e.key), style: const TextStyle(fontWeight: FontWeight.w700, color: muted, fontSize: 12)), const SizedBox(height: 3), DataView(data: e.value)]))).toList()); if (data is List) return Column(crossAxisAlignment: CrossAxisAlignment.start, children: (data as List).map<Widget>((x) => Padding(padding: const EdgeInsets.only(bottom: 10), child: DataView(data: x))).toList()); return SelectableText(human(data)); } }
class Stat extends StatelessWidget { const Stat(this.label, this.value, this.icon, {super.key}); final String label, value; final IconData icon; @override Widget build(BuildContext context) => SizedBox(width: 225, child: Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(label, style: const TextStyle(color: muted)), Icon(icon, color: green, size: 22)]), const SizedBox(height: 18), Text(value, style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w800, color: ink))]))); }

// Shared form dialog: validates locally, keeps the form open on API errors.
class FormItem {
  const FormItem(this.key, this.label, {this.value = '', this.required = true, this.numeric = false, this.options, this.lines = 1, this.secret = false});
  final String key, label, value; final bool required, numeric, secret; final Map<String, String>? options; final int lines;
}
Future<bool?> editDialog(BuildContext context, String title, List<FormItem> fields, Future<void> Function(Map<String, String>) submit, {String button = 'Save'}) => showDialog<bool>(context: context, barrierDismissible: false, builder: (context) => EntryDialog(title: title, fields: fields, submit: submit, button: button));
class EntryDialog extends StatefulWidget { const EntryDialog({super.key, required this.title, required this.fields, required this.submit, required this.button}); final String title, button; final List<FormItem> fields; final Future<void> Function(Map<String, String>) submit; @override State<EntryDialog> createState() => _EntryDialogState(); }
class _EntryDialogState extends State<EntryDialog> {
  final form = GlobalKey<FormState>(); late final Map<String, TextEditingController> values = {for (final f in widget.fields) f.key: TextEditingController(text: f.value)}; bool busy = false; String? error;
  @override void dispose() { for (final v in values.values) { v.dispose(); } super.dispose(); }
  Future<void> save() async { if (!form.currentState!.validate()) return; setState(() { busy = true; error = null; }); try { await widget.submit({for (final e in values.entries) e.key: e.value.text.trim()}); if (mounted) Navigator.pop(context, true); } catch (e) { if (mounted) setState(() { busy = false; error = e.toString(); }); } }
  @override Widget build(BuildContext context) => AlertDialog(title: Text(widget.title), content: SizedBox(width: 520, child: SingleChildScrollView(child: Form(key: form, child: Column(mainAxisSize: MainAxisSize.min, children: [if (error != null) Padding(padding: const EdgeInsets.only(bottom: 14), child: Text(error!, style: const TextStyle(color: Colors.red))), ...widget.fields.map((f) => Padding(padding: const EdgeInsets.only(bottom: 16), child: f.options != null ? DropdownButtonFormField<String>(value: values[f.key]!.text.isEmpty ? null : values[f.key]!.text, isExpanded: true, decoration: InputDecoration(labelText: f.label), items: f.options!.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value, overflow: TextOverflow.ellipsis))).toList(), onChanged: busy ? null : (v) => values[f.key]!.text = v ?? '', validator: (v) => f.required && (v == null || v.isEmpty) ? 'Choose an option' : null) : TextFormField(controller: values[f.key], obscureText: f.secret, maxLines: f.secret ? 1 : f.lines, decoration: InputDecoration(labelText: f.label), keyboardType: f.numeric ? const TextInputType.numberWithOptions(decimal: true, signed: true) : TextInputType.text, validator: (v) { if (f.required && (v == null || v.trim().isEmpty)) return 'This field is required'; if (f.numeric && (v?.isNotEmpty ?? false) && (double.tryParse(v!) == null || !double.parse(v).isFinite)) return 'Enter a valid number'; return null; }))), ])))), actions: [TextButton(onPressed: busy ? null : () => Navigator.pop(context, false), child: const Text('Cancel')), FilledButton(onPressed: busy ? null : save, child: Text(busy ? 'Saving…' : widget.button))]);
}
