import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../models.dart';
import '../services/streamer.dart';

class StreamScreen extends StatefulWidget {
  final PcTarget target;
  final Quality quality;
  final bool frontCamera;

  const StreamScreen({super.key, required this.target, required this.quality, required this.frontCamera});

  @override
  State<StreamScreen> createState() => _StreamScreenState();
}

class _StreamScreenState extends State<StreamScreen> {
  final _renderer = RTCVideoRenderer();
  late final Streamer _streamer;
  bool _previewOn = true;
  String? _fatal;

  @override
  void initState() {
    super.initState();
    _streamer = Streamer(target: widget.target, quality: widget.quality, frontCamera: widget.frontCamera);
    _start();
  }

  Future<void> _start() async {
    WakelockPlus.enable();
    try {
      await _renderer.initialize();
      final stream = await _streamer.openCamera();
      if (!mounted) return;
      setState(() => _renderer.srcObject = stream);
      _streamer.media.addListener(_onMediaChanged);
      _streamer.run();
    } catch (e) {
      setState(() => _fatal = 'No se pudo abrir la cámara: $e');
    }
  }

  void _onMediaChanged() {
    final s = _streamer.media.value;
    if (mounted && s != null) setState(() => _renderer.srcObject = s);
  }

  @override
  void dispose() {
    _streamer.media.removeListener(_onMediaChanged);
    WakelockPlus.disable();
    _renderer.srcObject = null;
    _renderer.dispose();
    _streamer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: _fatal != null
                  ? Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(_fatal!)))
                  : _previewOn
                      ? RTCVideoView(
                          _renderer,
                          mirror: _streamer.frontCamera,
                          objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitContain,
                        )
                      : const Center(
                          child: Text('Vista previa apagada (ahorra batería)',
                              style: TextStyle(color: Colors.white54)),
                        ),
            ),
            Positioned(
              top: 12,
              left: 12,
              right: 12,
              child: ValueListenableBuilder<bool>(
                valueListenable: _streamer.connected,
                builder: (_, ok, __) => ValueListenableBuilder<String>(
                  valueListenable: _streamer.status,
                  builder: (_, text, __) => Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.6),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.circle, size: 12, color: ok ? Colors.redAccent : Colors.amber),
                        const SizedBox(width: 8),
                        Expanded(child: Text(text, style: const TextStyle(color: Colors.white))),
                        Text(widget.quality.label.split(' (').first,
                            style: const TextStyle(color: Colors.white54, fontSize: 12)),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            Positioned(
              bottom: 16,
              left: 0,
              right: 0,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _RoundButton(
                    icon: _previewOn ? Icons.visibility : Icons.visibility_off,
                    tooltip: 'Vista previa',
                    onPressed: () => setState(() => _previewOn = !_previewOn),
                  ),
                  _RoundButton(
                    icon: Icons.stop,
                    tooltip: 'Detener',
                    color: Colors.redAccent,
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                  _RoundButton(
                    icon: Icons.cameraswitch,
                    tooltip: 'Cambiar cámara',
                    onPressed: () async {
                      await _streamer.switchCamera();
                      setState(() {});
                    },
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RoundButton extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;
  final Color? color;

  const _RoundButton({required this.icon, required this.tooltip, required this.onPressed, this.color});

  @override
  Widget build(BuildContext context) {
    return IconButton.filled(
      iconSize: 30,
      tooltip: tooltip,
      style: IconButton.styleFrom(
        backgroundColor: color ?? Colors.white24,
        padding: const EdgeInsets.all(16),
      ),
      onPressed: onPressed,
      icon: Icon(icon, color: Colors.white),
    );
  }
}
