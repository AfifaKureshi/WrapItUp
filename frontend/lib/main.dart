import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:file_picker/file_picker.dart';
import 'package:file_saver/file_saver.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:fl_chart/fl_chart.dart';

part 'core.dart';
part 'screens/auth.dart';
part 'screens/shell.dart';
part 'screens/brief.dart';
part 'screens/project.dart';
part 'screens/workspaces.dart';

void main() { WidgetsFlutterBinding.ensureInitialized(); runApp(PackWiseApp()); }

class PackWiseApp extends StatefulWidget {
  PackWiseApp({super.key, ApiClient? api}) : api = api ?? ApiClient();
  final ApiClient api;
  @override State<PackWiseApp> createState() => _PackWiseAppState();
}
class _PackWiseAppState extends State<PackWiseApp> {
  Map<String, dynamic>? user;
  bool starting = true;
  String? startupError;
  @override void initState() { super.initState(); widget.api.onUnauthorized = expired; restore(); }
  void expired() { if (mounted) setState(() { user = null; widget.api.offline = false; }); }
  Future<void> restore() async {
    try {
      await widget.api.restore();
      if (widget.api.token != null) {
        try { user = asMap(await widget.api.get('/api/auth/me')); }
        on ApiException catch (e) { if (e.status != 401) rethrow; }
        on NetworkException {
          final cached = widget.api.prefs?.getString('last_user');
          if (cached != null) { user = asMap(jsonDecode(cached)); widget.api.offline = true; }
        }
      }
    } catch (e) { startupError = e.toString(); }
    if (mounted) setState(() => starting = false);
  }
  Future<void> signedIn(Map<String, dynamic> value) async {
    await widget.api.prefs?.setString('last_user', jsonEncode(value));
    if (mounted) setState(() { user = value; startupError = null; });
  }
  Future<void> logout() async { await widget.api.logout(); if (mounted) setState(() => user = null); }
  @override Widget build(BuildContext context) => MaterialApp(
    title: 'PackWise • Packaging intelligence', debugShowCheckedModeBanner: false, theme: appTheme(),
    home: starting ? const Scaffold(body: Center(child: CircularProgressIndicator())) : user == null
      ? AuthScreen(api: widget.api, onSignedIn: signedIn, initialError: startupError)
      : Shell(key: ValueKey(user!['id']), api: widget.api, user: user!, onLogout: logout, onProfile: signedIn),
  );
}
