/// Una PC con el receptor PhoneCam. [hosts] son las IPs/nombres a probar en orden.
class PcTarget {
  final String name;
  final List<String> hosts;
  final int port;

  const PcTarget({required this.name, required this.hosts, required this.port});

  String get label => '${hosts.first}:$port';

  /// Interpreta `phonecam://connect?h=ip1,ip2&p=8765` (QR) o `192.168.1.5[:8765]` (manual).
  static PcTarget? parse(String raw, {int defaultPort = 8765}) {
    raw = raw.trim();
    if (raw.isEmpty) return null;
    if (raw.startsWith('phonecam://')) {
      final uri = Uri.tryParse(raw);
      final h = uri?.queryParameters['h'];
      if (uri == null || h == null || h.isEmpty) return null;
      final port = int.tryParse(uri.queryParameters['p'] ?? '') ?? defaultPort;
      final hosts = h.split(',').where((s) => s.isNotEmpty).toList();
      return PcTarget(name: hosts.first, hosts: hosts, port: port);
    }
    final parts = raw.split(':');
    final port = parts.length > 1 ? int.tryParse(parts[1]) : defaultPort;
    if (port == null || parts[0].isEmpty) return null;
    return PcTarget(name: parts[0], hosts: [parts[0]], port: port);
  }

  String encode() => 'phonecam://connect?h=${hosts.join(',')}&p=$port&n=${Uri.encodeComponent(name)}';

  static PcTarget? decode(String s) {
    final t = parse(s);
    final n = Uri.tryParse(s)?.queryParameters['n'];
    return t == null ? null : PcTarget(name: n ?? t.name, hosts: t.hosts, port: t.port);
  }
}

class Quality {
  final String label;
  final int width;
  final int height;
  final int fps;
  final int maxKbps;

  const Quality(this.label, this.width, this.height, this.fps, this.maxKbps);

  static const presets = [
    Quality('720p · 30 fps', 1280, 720, 30, 4000),
    Quality('720p · 60 fps', 1280, 720, 60, 6000),
    Quality('1080p · 30 fps', 1920, 1080, 30, 8000),
    Quality('1080p · 60 fps', 1920, 1080, 60, 12000),
    Quality('4K · 30 fps (si el teléfono lo soporta)', 3840, 2160, 30, 25000),
  ];
}
