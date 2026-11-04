import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../models.dart';

/// Escanea el QR que muestra la ventana de PhoneCam en la PC.
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  bool _done = false;

  void _onDetect(BarcodeCapture capture) {
    if (_done) return;
    for (final b in capture.barcodes) {
      final t = PcTarget.parse(b.rawValue ?? '');
      if (t != null) {
        _done = true;
        Navigator.of(context).pop(t);
        return;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Escanea el QR de la PC')),
      body: MobileScanner(onDetect: _onDetect),
    );
  }
}
