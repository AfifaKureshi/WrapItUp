part of '../main.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, required this.api, required this.onSignedIn, this.initialError});
  final ApiClient api; final Future<void> Function(Map<String, dynamic>) onSignedIn; final String? initialError;
  @override State<AuthScreen> createState() => _AuthScreenState();
}
class _AuthScreenState extends State<AuthScreen> {
  final form = GlobalKey<FormState>();
  final email = TextEditingController(), password = TextEditingController(), name = TextEditingController();
  bool registering = false, busy = false, hidden = true;
  String role = 'manufacturer'; String? error;
  List<Map<String, dynamic>> demos = []; bool configLoading = true;
  @override void initState() { super.initState(); error = widget.initialError; loadConfig(); }
  Future<void> loadConfig() async {
    try { final config = asMap(await widget.api.get('/api/config')); demos = asRows(config['demo_accounts']); }
    catch (e) { error = e.toString(); }
    if (mounted) setState(() => configLoading = false);
  }
  @override void dispose() { email.dispose(); password.dispose(); name.dispose(); super.dispose(); }
  Future<void> openServerSettings() async {
    final urlCtrl = TextEditingController(text: widget.api.baseUrl);
    String? testResult; bool testing = false; bool testSuccess = false;
    await showDialog<void>(context: context, builder: (ctx) => StatefulBuilder(builder: (ctx, setDlg) => AlertDialog(
      title: const Text('Backend Server Settings'),
      content: SizedBox(width: 460, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Configure the backend API URL. For Android emulators use 10.0.2.2. For physical phones, use your computer\'s Wi-Fi IP.', style: TextStyle(fontSize: 12, color: muted)),
        const SizedBox(height: 14),
        TextField(controller: urlCtrl, decoration: const InputDecoration(labelText: 'API Base URL', prefixIcon: Icon(Icons.dns_outlined))),
        const SizedBox(height: 12),
        const Text('Quick presets:', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: muted)),
        const SizedBox(height: 6),
        Wrap(spacing: 6, runSpacing: 6, children: [
          ActionChip(label: const Text('Emulator (10.0.2.2:8000)'), onPressed: () => setDlg(() => urlCtrl.text = 'http://10.0.2.2:8000')),
          ActionChip(label: const Text('Localhost (8000)'), onPressed: () => setDlg(() => urlCtrl.text = 'http://localhost:8000')),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(icon: testing ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.network_check_rounded, size: 16), label: const Text('Test Connection'), onPressed: testing ? null : () async {
          setDlg(() { testing = true; testResult = null; });
          final res = await widget.api.testConnection(urlCtrl.text);
          setDlg(() { testing = false; testSuccess = res['ok'] == true; testResult = testSuccess ? 'Connected successfully (${res['ms']} ms)' : 'Failed: ${res['error']}'; });
        }),
        if (testResult != null) ...[const SizedBox(height: 8), Text(testResult!, style: TextStyle(fontSize: 12, color: testSuccess ? Colors.green[800] : const Color(0xFF9B4529), fontWeight: FontWeight.w600))],
      ]))),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        FilledButton(onPressed: () async {
          await widget.api.setBaseUrl(urlCtrl.text);
          if (ctx.mounted) Navigator.pop(ctx);
          setState(() { error = null; configLoading = true; });
          loadConfig();
        }, child: const Text('Save & Reconnect')),
      ],
    )));
  }
  Future<void> submit() async {
    if (!form.currentState!.validate()) return;
    setState(() { busy = true; error = null; });
    try { final u = await widget.api.authenticate('/api/auth/${registering ? 'register' : 'login'}', {'email': email.text.trim(), 'password': password.text, if (registering) 'name': name.text.trim(), if (registering) 'role': role}); await widget.onSignedIn(u); }
    catch (e) { if (mounted) setState(() => error = e.toString()); }
    finally { if (mounted) setState(() => busy = false); }
  }
  @override Widget build(BuildContext context) => Scaffold(body: LayoutBuilder(builder: (context, box) {
    final wide = box.maxWidth >= 1000;
    final login = Center(child: SingleChildScrollView(padding: const EdgeInsets.all(32), child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 450), child: AutofillGroup(child: Form(key: form, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (!wide) ...[const Brand(), const SizedBox(height: 36)],
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        const Pill('FOOD PACKAGING INTELLIGENCE'),
        TextButton.icon(onPressed: openServerSettings, icon: const Icon(Icons.settings_outlined, size: 15), label: const Text('Server', style: TextStyle(fontSize: 12))),
      ]),
      const SizedBox(height: 22),
      Text(registering ? 'Your next better pack\nstarts here.' : 'Welcome back.', style: Theme.of(context).textTheme.headlineLarge), const SizedBox(height: 10),
      Text(registering ? 'Create a workspace for your products, trials and packaging decisions.' : 'Sign in to make your next packaging decision.', style: const TextStyle(color: muted, fontSize: 15)), const SizedBox(height: 28),
      if (error != null) ...[Container(width: double.infinity, padding: const EdgeInsets.all(14), decoration: BoxDecoration(color: const Color(0xFFFFEDE6), borderRadius: BorderRadius.circular(12)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(error!, style: const TextStyle(color: Color(0xFF9B4529))), const SizedBox(height: 6), InkWell(onTap: openServerSettings, child: const Text('Change server URL or emulator IP →', style: TextStyle(color: Color(0xFF9B4529), fontWeight: FontWeight.w700, decoration: TextDecoration.underline, fontSize: 12)))])) , const SizedBox(height: 16)],
      if (registering) ...[TextFormField(controller: name, decoration: const InputDecoration(labelText: 'Full name'), validator: (v) => (v?.trim().length ?? 0) < 2 ? 'Enter your name' : null), const SizedBox(height: 16), DropdownButtonFormField<String>(value: role, decoration: const InputDecoration(labelText: 'Your workspace'), items: ['farmer', 'manufacturer', 'researcher'].map((v) => DropdownMenuItem(value: v, child: Text(human(v)))).toList(), onChanged: (v) => setState(() => role = v!)), const SizedBox(height: 16)],
      TextFormField(key: const Key('email'), controller: email, autofillHints: const [AutofillHints.email], keyboardType: TextInputType.emailAddress, decoration: const InputDecoration(labelText: 'Email address', prefixIcon: Icon(Icons.mail_outline_rounded)), validator: (v) => v == null || !RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(v.trim()) ? 'Enter a valid email address' : null), const SizedBox(height: 16),
      TextFormField(key: const Key('password'), controller: password, autofillHints: [registering ? AutofillHints.newPassword : AutofillHints.password], obscureText: hidden, decoration: InputDecoration(labelText: 'Password', prefixIcon: const Icon(Icons.lock_outline_rounded), suffixIcon: IconButton(tooltip: hidden ? 'Show password' : 'Hide password', onPressed: () => setState(() => hidden = !hidden), icon: Icon(hidden ? Icons.visibility_outlined : Icons.visibility_off_outlined))), onFieldSubmitted: (_) => busy ? null : submit(), validator: (v) => (v?.length ?? 0) < (registering ? 10 : 1) ? (registering ? 'Use at least 10 characters' : 'Enter your password') : null),
      const SizedBox(height: 24), SizedBox(width: double.infinity, child: FilledButton.icon(key: const Key('sign-in'), onPressed: busy ? null : submit, label: Text(busy ? 'Please wait…' : registering ? 'Create account' : 'Sign in to workspace'), icon: const Icon(Icons.arrow_forward_rounded, size: 19))),
      const SizedBox(height: 16), Center(child: TextButton(onPressed: busy ? null : () => setState(() { registering = !registering; error = null; }), child: Text(registering ? 'Already have an account? Sign in' : 'New to PackWise? Create an account'))),
      if (!registering) ...[const SizedBox(height: 18), const Divider(), const SizedBox(height: 20), Text(configLoading ? 'Checking demo availability…' : demos.isEmpty ? 'Use your registered account to continue.' : 'EXPLORE A DEMO WORKSPACE', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: muted, letterSpacing: 1.2)), const SizedBox(height: 12), Wrap(spacing: 8, runSpacing: 8, children: demos.map((d) => OutlinedButton.icon(key: Key('demo-${d['role']}'), onPressed: busy ? null : () => setState(() { email.text = d['email'] as String; password.text = d['password'] as String; role = d['role'] as String; error = null; }), icon: Icon(roleIcon(d['role']), size: 17), label: Text(titleCase(d['role'])))).toList()), if (demos.isNotEmpty) ...[const SizedBox(height: 10), const Text('Choose a role to fill valid credentials, then sign in.', style: TextStyle(color: muted, fontSize: 12))], if (error != null && demos.isEmpty) Row(children: [TextButton(onPressed: loadConfig, child: const Text('Retry connection')), const SizedBox(width: 8), TextButton(onPressed: openServerSettings, child: const Text('Configure server'))])],
      const SizedBox(height: 24), const Text('PS 236  ·  Built for better food journeys', style: TextStyle(color: muted, fontSize: 12)),
    ]))))));
    return Row(children: [if (wide) Expanded(child: Container(margin: const EdgeInsets.all(18), padding: const EdgeInsets.all(44), decoration: BoxDecoration(color: ink, borderRadius: BorderRadius.circular(28)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [const Brand(light: true), const Spacer(), const Text('Less guesswork.\nBetter packaging.\nLonger possibilities.', style: TextStyle(fontSize: 44, height: 1.1, letterSpacing: -1.5, fontWeight: FontWeight.w800, color: Colors.white)), const SizedBox(height: 22), const Text('A connected workspace for farmers,\nfood manufacturers and packaging researchers.', style: TextStyle(color: Color(0xFFB4CEC3), fontSize: 16, height: 1.6)), const SizedBox(height: 34), const SizedBox(height: 200, child: PackagingArt()), const Spacer(), const Row(children: [Icon(Icons.science_outlined, color: lime, size: 20), SizedBox(width: 10), Expanded(child: Text('Clear assumptions. Traceable decisions.', style: TextStyle(color: Colors.white70, fontSize: 13)))]), ]))), Expanded(child: login)]);
  }));
}
String titleCase(dynamic s) { final text = human(s); return text.isEmpty ? text : text[0].toUpperCase() + text.substring(1); }
IconData roleIcon(dynamic role) => role == 'farmer' ? Icons.agriculture_outlined : role == 'researcher' ? Icons.science_outlined : Icons.factory_outlined;
class Brand extends StatelessWidget { const Brand({super.key, this.light = false}); final bool light; @override Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [Container(padding: const EdgeInsets.all(9), decoration: BoxDecoration(color: light ? lime : green, borderRadius: BorderRadius.circular(12)), child: Icon(Icons.layers_rounded, color: light ? ink : Colors.white, size: 26)), const SizedBox(width: 12), Text('PackWise', style: TextStyle(fontSize: 24, letterSpacing: -.8, fontWeight: FontWeight.w800, color: light ? Colors.white : ink))]); }
class PackagingArt extends StatelessWidget { const PackagingArt({super.key}); @override Widget build(BuildContext context) => LayoutBuilder(builder: (context, box) => Stack(alignment: Alignment.center, children: [Positioned(left: 10, right: 10, bottom: 3, child: Container(height: 1, color: Colors.white24)), Transform.rotate(angle: -.09, child: Container(width: 126, height: 172, margin: const EdgeInsets.only(right: 120), decoration: BoxDecoration(color: lime, borderRadius: BorderRadius.circular(16)), child: const Column(mainAxisAlignment: MainAxisAlignment.center, children: [Icon(Icons.eco_rounded, size: 46, color: ink), SizedBox(height: 12), Text('FRESH THINKING', style: TextStyle(fontSize: 10, letterSpacing: 1, fontWeight: FontWeight.w800)), SizedBox(height: 6), Text('Better by design', style: TextStyle(fontSize: 10))]))), Transform.rotate(angle: .08, child: Container(width: 122, height: 153, margin: const EdgeInsets.only(left: 116, top: 25), decoration: BoxDecoration(color: const Color(0xFFE7B886), borderRadius: BorderRadius.circular(14)), child: const Column(mainAxisAlignment: MainAxisAlignment.center, children: [Icon(Icons.grain_rounded, size: 45, color: ink), SizedBox(height: 12), Text('PACKED WITH CARE', style: TextStyle(fontSize: 9, fontWeight: FontWeight.w800, letterSpacing: 1))])))])); }
