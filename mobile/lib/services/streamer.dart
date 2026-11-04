import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

import '../models.dart';
import 'discovery.dart';

/// Captura la cámara y la envía a la PC por WebRTC. La cámara se queda abierta
/// y, si la conexión se cae, se reconecta sola cada pocos segundos.
class Streamer {
  final PcTarget target;
  final Quality quality;
  bool frontCamera;

  final ValueNotifier<String> status = ValueNotifier('Abriendo cámara…');
  final ValueNotifier<bool> connected = ValueNotifier(false);

  MediaStream? stream;
  RTCPeerConnection? _pc;
  RTCRtpSender? _sender;
  WebSocket? _ws;
  bool _closed = false;

  Streamer({required this.target, required this.quality, this.frontCamera = false});

  Future<MediaStream> openCamera() async {
    final s = await navigator.mediaDevices.getUserMedia({
      'audio': false,
      'video': {
        'facingMode': frontCamera ? 'user' : 'environment',
        'width': quality.width,
        'height': quality.height,
        'frameRate': quality.fps,
      },
    });
    stream = s;
    return s;
  }

  Future<void> switchCamera() async {
    final track = stream?.getVideoTracks().firstOrNull;
    if (track == null) return;
    await Helper.switchCamera(track);
    frontCamera = !frontCamera;
  }

  /// Bucle de conexión; termina solo cuando se llama a [dispose].
  Future<void> run() async {
    while (!_closed) {
      try {
        await _session();
      } catch (e) {
        if (!_closed) status.value = _humanError(e);
      }
      connected.value = false;
      if (_closed) break;
      await Future.delayed(const Duration(seconds: 2));
      if (!_closed && !status.value.startsWith('No se')) status.value = 'Reconectando…';
    }
  }

  Future<void> _session() async {
    status.value = 'Buscando ${target.name}…';
    final host = await findReachableHost(target);
    if (host == null) {
      throw 'No se encuentra la PC (${target.label}). ¿Está abierto PhoneCam y en la misma red?';
    }
    if (_closed) return;

    status.value = 'Conectando…';
    final ws = await WebSocket.connect('ws://$host:${target.port}/ws')
        .timeout(const Duration(seconds: 5));
    ws.pingInterval = const Duration(seconds: 3);
    _ws = ws;

    final pc = await createPeerConnection({'iceServers': [], 'sdpSemantics': 'unified-plan'});
    _pc = pc;
    final track = stream!.getVideoTracks().first;
    _sender = await pc.addTrack(track, stream!);

    final done = Completer<void>();
    void finish() {
      if (!done.isCompleted) done.complete();
    }

    pc.onConnectionState = (state) {
      switch (state) {
        case RTCPeerConnectionState.RTCPeerConnectionStateConnected:
          connected.value = true;
          status.value = 'Transmitiendo a ${target.name}';
          _applyBitrate();
          break;
        case RTCPeerConnectionState.RTCPeerConnectionStateFailed:
        case RTCPeerConnectionState.RTCPeerConnectionStateClosed:
          finish();
          break;
        default:
          break;
      }
    };

    // Sin "trickle": esperamos a tener los candidatos ICE y mandamos una sola oferta.
    final gathered = Completer<void>();
    pc.onIceGatheringState = (s) {
      if (s == RTCIceGatheringState.RTCIceGatheringStateComplete && !gathered.isCompleted) {
        gathered.complete();
      }
    };
    final offer = await pc.createOffer({'offerToReceiveVideo': false, 'offerToReceiveAudio': false});
    await pc.setLocalDescription(offer);
    await gathered.future.timeout(const Duration(seconds: 2), onTimeout: () {});
    final local = await pc.getLocalDescription();

    ws.listen(
      (raw) async {
        final msg = jsonDecode(raw as String) as Map<String, dynamic>;
        if (msg['type'] == 'answer') {
          final sdp = boostBitrate(msg['sdp'] as String, quality.maxKbps);
          await pc.setRemoteDescription(RTCSessionDescription(sdp, 'answer'));
        } else if (msg['type'] == 'bye') {
          if (msg['reason'] == 'replaced') status.value = 'Otro dispositivo tomó la cámara';
          finish();
        }
      },
      onDone: finish,
      onError: (_) => finish(),
      cancelOnError: true,
    );
    ws.add(jsonEncode({
      'type': 'offer',
      'sdp': local!.sdp,
      'device': 'Android',
    }));

    try {
      await done.future;
    } finally {
      await _teardown();
    }
  }

  Future<void> _applyBitrate() async {
    final sender = _sender;
    if (sender == null) return;
    try {
      final p = sender.parameters;
      final encs = p.encodings;
      if (encs == null || encs.isEmpty) {
        p.encodings = [RTCRtpEncoding(maxBitrate: quality.maxKbps * 1000, maxFramerate: quality.fps)];
      } else {
        for (final e in encs) {
          e.maxBitrate = quality.maxKbps * 1000;
          e.maxFramerate = quality.fps;
        }
      }
      await sender.setParameters(p);
    } catch (e) {
      debugPrint('setParameters falló: $e');
    }
  }

  Future<void> _teardown() async {
    final ws = _ws, pc = _pc;
    _ws = null;
    _pc = null;
    _sender = null;
    try {
      ws?.add(jsonEncode({'type': 'bye'}));
      await ws?.close();
    } catch (_) {}
    try {
      await pc?.close();
    } catch (_) {}
  }

  Future<void> dispose() async {
    _closed = true;
    await _teardown();
    for (final t in stream?.getTracks() ?? <MediaStreamTrack>[]) {
      await t.stop();
    }
    await stream?.dispose();
    stream = null;
  }

  static String _humanError(Object e) {
    if (e is String) return e;
    if (e is TimeoutException) return 'La PC no respondió a tiempo. Revisa el firewall de Windows.';
    if (e is SocketException) return 'Sin conexión con la PC: ${e.osError?.message ?? e.message}';
    return 'Error: $e';
  }
}

/// En la red local hay ancho de banda de sobra: le pedimos al codificador que
/// arranque alto en lugar de subir poco a poco desde ~300 kbps.
@visibleForTesting
String boostBitrate(String sdp, int maxKbps) {
  final lines = sdp.split('\r\n');
  final out = <String>[];
  final start = (maxKbps * 0.6).round();
  final min = (maxKbps * 0.25).round();
  final params = 'x-google-start-bitrate=$start;x-google-min-bitrate=$min;x-google-max-bitrate=$maxKbps';
  final videoPts = <String>{};
  final withFmtp = <String>{};
  final rtpmap = RegExp(r'^a=rtpmap:(\d+) (VP8|VP9|H264)/90000');
  for (final l in lines) {
    final m = rtpmap.firstMatch(l);
    if (m != null) videoPts.add(m.group(1)!);
  }
  var inVideo = false;
  for (final l in lines) {
    if (l.startsWith('m=')) inVideo = l.startsWith('m=video');
    final fmtp = RegExp(r'^a=fmtp:(\d+) ').firstMatch(l);
    if (fmtp != null && videoPts.contains(fmtp.group(1))) {
      withFmtp.add(fmtp.group(1)!);
      out.add('$l;$params');
      continue;
    }
    out.add(l);
    final m = rtpmap.firstMatch(l);
    if (m != null && !lines.any((x) => x.startsWith('a=fmtp:${m.group(1)} '))) {
      out.add('a=fmtp:${m.group(1)} $params');
    }
    if (inVideo && l.startsWith('c=')) out.add('b=AS:$maxKbps');
  }
  return out.join('\r\n');
}
