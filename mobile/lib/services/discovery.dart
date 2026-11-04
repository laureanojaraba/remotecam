import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:bonsoir/bonsoir.dart';
import 'package:flutter/foundation.dart';

import '../models.dart';

/// Busca PCs con el receptor anunciándose por mDNS como `_phonecam._tcp`.
class DiscoveryService {
  final ValueNotifier<List<PcTarget>> found = ValueNotifier(const []);
  BonsoirDiscovery? _discovery;
  StreamSubscription? _sub;
  final Map<String, PcTarget> _byName = {};

  Future<void> start() async {
    await stop();
    final d = BonsoirDiscovery(type: '_phonecam._tcp');
    _discovery = d;
    await d.ready;
    _sub = d.eventStream?.listen((event) {
      final service = event.service;
      if (service == null) return;
      switch (event.type) {
        case BonsoirDiscoveryEventType.discoveryServiceFound:
          service.resolve(d.serviceResolver);
          break;
        case BonsoirDiscoveryEventType.discoveryServiceResolved:
          if (service is ResolvedBonsoirService) {
            final ips = (service.attributes['ips'] ?? '')
                .split(',')
                .where((s) => s.isNotEmpty)
                .toList();
            final hosts = <String>{...ips, if (service.host != null) service.host!}.toList();
            if (hosts.isEmpty) return;
            _byName[service.name] = PcTarget(
              name: service.attributes['name'] ?? service.name,
              hosts: hosts,
              port: service.port,
            );
            found.value = _byName.values.toList();
          }
          break;
        case BonsoirDiscoveryEventType.discoveryServiceLost:
          _byName.remove(service.name);
          found.value = _byName.values.toList();
          break;
        default:
          break;
      }
    });
    await d.start();
  }

  Future<void> stop() async {
    await _sub?.cancel();
    _sub = null;
    final d = _discovery;
    _discovery = null;
    try {
      await d?.stop();
    } catch (_) {}
  }
}

/// Prueba cada host de [t] y devuelve el primero que responde como PhoneCam.
Future<String?> findReachableHost(PcTarget t,
    {Duration timeout = const Duration(seconds: 2)}) async {
  for (final host in t.hosts) {
    final client = HttpClient()..connectionTimeout = timeout;
    try {
      final req = await client.getUrl(Uri(scheme: 'http', host: host, port: t.port, path: '/info'));
      final res = await req.close().timeout(timeout);
      final body = await res.transform(utf8.decoder).join().timeout(timeout);
      if (res.statusCode == 200 && (jsonDecode(body) as Map)['app'] == 'phonecam') return host;
    } catch (_) {
      // probar el siguiente
    } finally {
      client.close(force: true);
    }
  }
  return null;
}
