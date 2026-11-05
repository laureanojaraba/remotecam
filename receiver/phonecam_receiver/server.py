"""Servidor de señalización WebRTC + recepción de video.

Protocolo (WebSocket en /ws, mensajes JSON):
  teléfono -> PC: {"type": "offer", "sdp": "...", "device": "Pixel 8"}
  PC -> teléfono: {"type": "answer", "sdp": "..."}
  cualquiera:     {"type": "bye"}
Solo hay una sesión activa: una conexión nueva reemplaza a la anterior.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

from aiohttp import WSMsgType, web
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError

from . import __version__
from .output import FramePipeline

log = logging.getLogger(__name__)
STALL_TIMEOUT = 8.0  # s sin frames estando conectado -> reconectar


class ReceiverServer:
    def __init__(
        self,
        pipeline: FramePipeline,
        name: str,
        port: int,
        on_event: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.pipeline = pipeline
        self.name = name
        self.port = port
        self.on_event = on_event or (lambda e: None)
        self._pc: Optional[RTCPeerConnection] = None
        self._ws: Optional[web.WebSocketResponse] = None
        self._consumer: Optional[asyncio.Task] = None
        self._runner: Optional[web.AppRunner] = None

    # ------------------------------------------------------------------ HTTP
    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/info", self._info)
        app.router.add_get("/ws", self._ws_handler)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, "0.0.0.0", self.port).start()
        log.info("Escuchando en el puerto %d", self.port)

    async def stop(self) -> None:
        await self._close_session()
        if self._runner:
            await self._runner.cleanup()

    async def _info(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"app": "phonecam", "name": self.name, "version": __version__, "proto": 1,
             "busy": self._pc is not None}
        )

    # ------------------------------------------------------------- sesiones
    async def _close_session(self, reason: str = "replaced") -> None:
        pc, ws, task = self._pc, self._ws, self._consumer
        self._pc = self._ws = self._consumer = None
        if task and task is not asyncio.current_task():
            task.cancel()
        if ws and not ws.closed:
            try:
                await ws.send_json({"type": "bye", "reason": reason})
            except Exception:
                pass
            await ws.close()
        if pc:
            await pc.close()

    async def _consume(self, track, pc: RTCPeerConnection, device: str) -> None:
        self.on_event({"event": "streaming"})
        self.pipeline.set_idle_text("Esperando telefono...")
        try:
            while True:
                frame = await asyncio.wait_for(track.recv(), timeout=STALL_TIMEOUT)
                self.pipeline.submit(frame)
        except asyncio.TimeoutError:
            # La conexión sigue viva pero el video se detuvo: cerramos la sesión para
            # que el teléfono reinicie la cámara y se reconecte solo.
            if self._pc is pc:
                log.warning("Sin video durante %ss; se fuerza la reconexión", STALL_TIMEOUT)
                await self._close_session(reason="stalled")
                self.on_event({"event": "disconnected", "device": device})
        except (MediaStreamError, asyncio.CancelledError):
            pass
        finally:
            log.info("Fin del video")

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=4.0)
        await ws.prepare(request)
        peer = request.remote
        log.info("Teléfono conectado desde %s", peer)

        await self._close_session()
        # Sin STUN: en red local basta con los candidatos 'host' y conecta al instante.
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self._pc, self._ws = pc, ws
        device = peer

        @pc.on("track")
        def on_track(track):
            if track.kind == "video" and self._pc is pc:
                self._consumer = asyncio.ensure_future(self._consume(track, pc, device))

        @pc.on("connectionstatechange")
        async def on_state():
            log.info("Estado WebRTC: %s", pc.connectionState)
            if self._pc is pc:
                self.on_event({"event": "state", "state": pc.connectionState, "device": device})
                if pc.connectionState == "failed":
                    await self._close_session()

        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                kind = data.get("type")
                if kind == "offer":
                    device = data.get("device") or peer
                    self.on_event({"event": "connecting", "device": device})
                    await pc.setRemoteDescription(RTCSessionDescription(sdp=data["sdp"], type="offer"))
                    answer = await pc.createAnswer()
                    await pc.setLocalDescription(answer)  # aiortc incluye ya los candidatos ICE
                    await ws.send_json({"type": "answer", "sdp": pc.localDescription.sdp})
                elif kind == "bye":
                    break
                elif kind == "ping":
                    await ws.send_json({"type": "pong"})
        except Exception:
            log.exception("Error en la sesión")
        finally:
            if self._pc is pc:
                await self._close_session()
                self.on_event({"event": "disconnected", "device": device})
            log.info("Teléfono desconectado (%s)", device)
        return ws
