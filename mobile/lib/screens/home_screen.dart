import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models.dart';
import '../services/discovery.dart';
import 'scan_screen.dart';
import 'stream_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _discovery = DiscoveryService();
  PcTarget? _last;
  int _qualityIndex = 2; // 1080p30
  bool _front = false;

  @override
  void initState() {
    super.initState();
    _load();
    _discovery.start().catchError((e) => debugPrint('mDNS: $e'));
  }

  Future<void> _load() async {
    final p = await SharedPreferences.getInstance();
    setState(() {
      final last = p.getString('last_pc');
      _last = last == null ? null : PcTarget.decode(last);
      _qualityIndex = (p.getInt('quality') ?? 2).clamp(0, Quality.presets.length - 1);
      _front = p.getBool('front') ?? false;
    });
  }

  Future<void> _savePrefs() async {
    final p = await SharedPreferences.getInstance();
    await p.setInt('quality', _qualityIndex);
    await p.setBool('front', _front);
  }

  @override
  void dispose() {
    _discovery.stop();
    super.dispose();
  }

  Future<void> _connect(PcTarget target) async {
    if (!await Permission.camera.request().isGranted) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('PhoneCam necesita permiso de cámara'),
          action: SnackBarAction(label: 'Ajustes', onPressed: openAppSettings),
        ),
      );
      return;
    }
    final p = await SharedPreferences.getInstance();
    await p.setString('last_pc', target.encode());
    setState(() => _last = target);
    await _discovery.stop(); // libera la red/CPU mientras transmite
    if (!mounted) return;
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => StreamScreen(
        target: target,
        quality: Quality.presets[_qualityIndex],
        frontCamera: _front,
      ),
    ));
    _discovery.start().catchError((e) => debugPrint('mDNS: $e'));
  }

  Future<void> _scan() async {
    final t = await Navigator.of(context).push<PcTarget>(
      MaterialPageRoute(builder: (_) => const ScanScreen()),
    );
    if (t != null) await _connect(t);
  }

  Future<void> _manual() async {
    final ctrl = TextEditingController(text: _last?.label ?? '');
    final value = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Dirección de la PC'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(hintText: '192.168.1.20:8765'),
          onSubmitted: (v) => Navigator.pop(ctx, v),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text), child: const Text('Conectar')),
        ],
      ),
    );
    final t = value == null ? null : PcTarget.parse(value);
    if (t != null) await _connect(t);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('PhoneCam')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('PCs en tu red', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          ValueListenableBuilder<List<PcTarget>>(
            valueListenable: _discovery.found,
            builder: (_, pcs, __) {
              if (pcs.isEmpty) {
                return const Card(
                  child: ListTile(
                    leading: SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)),
                    title: Text('Buscando…'),
                    subtitle: Text('Abre PhoneCam en la PC y conecta ambos a la misma red Wi-Fi.'),
                  ),
                );
              }
              return Column(
                children: [
                  for (final pc in pcs)
                    Card(
                      child: ListTile(
                        leading: const Icon(Icons.computer),
                        title: Text(pc.name),
                        subtitle: Text(pc.label),
                        trailing: const Icon(Icons.play_arrow),
                        onTap: () => _connect(pc),
                      ),
                    ),
                ],
              );
            },
          ),
          if (_last != null) ...[
            const SizedBox(height: 8),
            Card(
              child: ListTile(
                leading: const Icon(Icons.history),
                title: Text('Última: ${_last!.name}'),
                subtitle: Text(_last!.label),
                onTap: () => _connect(_last!),
              ),
            ),
          ],
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: _scan,
                  icon: const Icon(Icons.qr_code_scanner),
                  label: const Text('Escanear QR'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _manual,
                  icon: const Icon(Icons.edit),
                  label: const Text('IP manual'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          Text('Calidad', style: theme.textTheme.titleMedium),
          const SizedBox(height: 4),
          DropdownButtonFormField<int>(
            value: _qualityIndex,
            items: [
              for (var i = 0; i < Quality.presets.length; i++)
                DropdownMenuItem(value: i, child: Text(Quality.presets[i].label)),
            ],
            onChanged: (v) {
              setState(() => _qualityIndex = v ?? _qualityIndex);
              _savePrefs();
            },
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Empezar con la cámara frontal'),
            value: _front,
            onChanged: (v) {
              setState(() => _front = v);
              _savePrefs();
            },
          ),
          const SizedBox(height: 8),
          Text(
            'Consejo: pon el teléfono en horizontal para llenar el cuadro 16:9. '
            'Sin Wi-Fi, activa "Anclaje USB" y conecta el cable: funciona igual.',
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
