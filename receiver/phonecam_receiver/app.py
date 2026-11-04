"""Une el pipeline de video, el servidor y el anuncio mDNS en un hilo de asyncio."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import socket
import threading
from dataclasses import asdict
from pathlib import Path

from .discovery import Announcer
from .output import FramePipeline, OutputConfig, make_output
from .server import ReceiverServer

log = logging.getLogger(__name__)
DEFAULT_PORT = 8765


def config_path() -> Path:
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / "PhoneCam" / "config.json"


def load_config() -> OutputConfig:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        fields = OutputConfig.__dataclass_fields__
        return OutputConfig(**{k: v for k, v in data.items() if k in fields})
    except (OSError, ValueError, TypeError):
        return OutputConfig()


def save_config(cfg: OutputConfig) -> None:
    try:
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("No se pudo guardar la configuración: %s", e)


class ReceiverApp:
    def __init__(self, cfg: OutputConfig, output_kind: str = "virtualcam", port: int = DEFAULT_PORT,
                 name: str | None = None, backend: str | None = None) -> None:
        self.name = name or socket.gethostname()
        self.port = port
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.pipeline = FramePipeline(make_output(output_kind, backend), cfg,
                                      on_stats=lambda s: self.events.put({"event": "stats", **s}))
        self.server = ReceiverServer(self.pipeline, self.name, port, on_event=self.events.put)
        self.announcer = Announcer(self.name, port)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_evt = asyncio.Event()
        await self.server.start()
        await self.announcer.start()
        self.events.put({"event": "ready", "ips": self.announcer.ips, "port": self.port})
        try:
            await self._stop_evt.wait()
        finally:
            await self.announcer.stop()
            await self.server.stop()

    def start_background(self) -> None:
        self.pipeline.start()

        def runner():
            try:
                asyncio.run(self._main())
            except OSError as e:  # p.ej. puerto ocupado
                self.events.put({"event": "fatal", "error": str(e)})
            finally:
                self._stopped.set()

        self._thread = threading.Thread(target=runner, name="asyncio", daemon=True)
        self._thread.start()

    def run_forever(self) -> None:
        self.start_background()
        try:
            while not self._stopped.is_set():
                try:
                    ev = self.events.get(timeout=0.5)
                except queue.Empty:
                    continue
                if ev["event"] == "stats":
                    if ev["streaming"]:
                        log.info("%.1f fps  entrada=%s  salida=%s  descartados=%d",
                                 ev["fps"], ev["input"], ev["output"], ev["dropped"])
                elif ev["event"] == "ready":
                    log.info("Listo. IPs: %s  puerto %d", ", ".join(ev["ips"]), ev["port"])
                    log.info("QR: %s", self.announcer.qr_payload())
                elif ev["event"] == "fatal":
                    log.error(ev["error"])
                else:
                    log.info("Evento: %s", ev)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self._loop and not self._stopped.is_set():
            self._loop.call_soon_threadsafe(self._stop_evt.set)
            self._stopped.wait(timeout=5)
        self.pipeline.stop()
