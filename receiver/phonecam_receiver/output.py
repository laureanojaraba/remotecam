"""Salida de video: cámara virtual, ventana de vista previa o nula (pruebas).

El `FramePipeline` corre en su propio hilo: recibe el último frame decodificado,
descarta los atrasados (para no acumular latencia), lo ajusta a la resolución de
salida y lo envía a la cámara virtual. Si no llega video, muestra una imagen de
"esperando teléfono" para que Zoom/Meet/OBS no se queden congelados.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutputConfig:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    mode: str = "fit"  # "fit" = barras negras, "fill" = recortar para llenar
    mirror: bool = False


def compose(rgb: np.ndarray, cfg: OutputConfig) -> np.ndarray:
    """Ajusta un frame RGB (h, w, 3) al tamaño de salida respetando la proporción."""
    h, w = rgb.shape[:2]
    W, H = cfg.width, cfg.height
    if (w, h) == (W, H):
        out = rgb
    else:
        scale = min(W / w, H / h) if cfg.mode == "fit" else max(W / w, H / h)
        sw, sh = max(1, round(w * scale)), max(1, round(h * scale))
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        scaled = cv2.resize(rgb, (sw, sh), interpolation=interp)
        if cfg.mode == "fit":
            out = np.zeros((H, W, 3), dtype=np.uint8)
            x, y = (W - sw) // 2, (H - sh) // 2
            out[y : y + sh, x : x + sw] = scaled
        else:
            x, y = (sw - W) // 2, (sh - H) // 2
            out = scaled[y : y + H, x : x + W]
    if cfg.mirror:
        out = out[:, ::-1]
    return np.ascontiguousarray(out)


def placeholder(cfg: OutputConfig, text: str) -> np.ndarray:
    img = np.full((cfg.height, cfg.width, 3), 24, dtype=np.uint8)
    scale = cfg.height / 720
    font = cv2.FONT_HERSHEY_SIMPLEX
    for i, (line, size) in enumerate(((text, 1.4), ("PhoneCam", 0.9))):
        (tw, th), _ = cv2.getTextSize(line, font, size * scale, max(1, int(2 * scale)))
        org = ((cfg.width - tw) // 2, cfg.height // 2 + int((i * 70 - 10) * scale))
        color = (230, 230, 230) if i == 0 else (120, 160, 255)
        cv2.putText(img, line, org, font, size * scale, color, max(1, int(2 * scale)), cv2.LINE_AA)
    return img


# --------------------------------------------------------------------------- outputs


class Output:
    name = "base"

    def open(self, cfg: OutputConfig) -> None: ...
    def send(self, rgb: np.ndarray) -> None: ...
    def close(self) -> None: ...


class NullOutput(Output):
    name = "null"

    def __init__(self) -> None:
        self.frames_sent = 0

    def send(self, rgb: np.ndarray) -> None:
        self.frames_sent += 1


class VirtualCamOutput(Output):
    """Cámara virtual vía pyvirtualcam (en Windows usa el driver de OBS o Unity Capture)."""

    def __init__(self, backend: Optional[str] = None) -> None:
        self.backend = backend
        self.cam = None
        self.name = "virtualcam"

    def open(self, cfg: OutputConfig) -> None:
        import pyvirtualcam

        self.cam = pyvirtualcam.Camera(
            width=cfg.width,
            height=cfg.height,
            fps=cfg.fps,
            fmt=pyvirtualcam.PixelFormat.RGB,
            backend=self.backend,
        )
        self.name = f"virtualcam ({self.cam.backend}: {self.cam.device})"
        log.info("Cámara virtual abierta: %s %dx%d@%d", self.cam.device, cfg.width, cfg.height, cfg.fps)

    def send(self, rgb: np.ndarray) -> None:
        self.cam.send(rgb)

    def close(self) -> None:
        if self.cam is not None:
            self.cam.close()
            self.cam = None


class PreviewOutput(Output):
    """Ventana de OpenCV, útil para probar sin cámara virtual."""

    name = "preview"

    def send(self, rgb: np.ndarray) -> None:
        cv2.imshow("PhoneCam preview", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        cv2.waitKey(1)

    def close(self) -> None:
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass


def make_output(kind: str, backend: Optional[str] = None) -> Output:
    if kind == "virtualcam":
        return VirtualCamOutput(backend)
    if kind == "preview":
        return PreviewOutput()
    if kind == "null":
        return NullOutput()
    raise ValueError(f"Salida desconocida: {kind}")


# --------------------------------------------------------------------------- pipeline


class FramePipeline(threading.Thread):
    """Hilo que convierte y envía frames; siempre procesa el más reciente."""

    IDLE_AFTER = 1.0  # s sin frames -> mostrar placeholder

    def __init__(
        self,
        output: Output,
        cfg: OutputConfig,
        on_stats: Optional[Callable[[dict], None]] = None,
    ) -> None:
        super().__init__(name="FramePipeline", daemon=True)
        self.output = output
        self._cfg = cfg
        self._reopen = True
        self._on_stats = on_stats
        self._cond = threading.Condition()
        self._latest = None  # av.VideoFrame o np.ndarray RGB
        self._stopping = False
        self._idle_text = "Esperando telefono..."
        self.error: Optional[str] = None
        # estadísticas
        self.received = 0
        self.dropped = 0
        self.sent = 0
        self.input_size: Optional[tuple[int, int]] = None
        self._last_frame_at = 0.0

    # -- API usada desde el hilo de asyncio / GUI
    @property
    def cfg(self) -> OutputConfig:
        return self._cfg

    def set_config(self, **changes) -> None:
        with self._cond:
            new = replace(self._cfg, **changes)
            if (new.width, new.height, new.fps) != (self._cfg.width, self._cfg.height, self._cfg.fps):
                self._reopen = True
            self._cfg = new
            self._cond.notify()

    def set_idle_text(self, text: str) -> None:
        self._idle_text = text

    def submit(self, frame) -> None:
        with self._cond:
            if self._latest is not None:
                self.dropped += 1
            self._latest = frame
            self.received += 1
            self._last_frame_at = time.monotonic()
            self._cond.notify()

    def stop(self) -> None:
        with self._cond:
            self._stopping = True
            self._cond.notify()
        self.join(timeout=3)

    # -- hilo
    def _open(self, cfg: OutputConfig) -> bool:
        try:
            self.output.close()
            self.output.open(cfg)
            self.error = None
            return True
        except Exception as e:  # driver no instalado, cámara en uso, etc.
            self.error = str(e)
            log.error("No se pudo abrir la salida: %s", e)
            return False

    def run(self) -> None:
        last_stats = time.monotonic()
        last_received = 0
        opened = False
        try:
            while True:
                with self._cond:
                    if self._latest is None and not self._stopping and not self._reopen:
                        self._cond.wait(timeout=0.2)
                    if self._stopping:
                        return
                    frame, self._latest = self._latest, None
                    cfg, reopen = self._cfg, self._reopen
                    self._reopen = False
                    idle = time.monotonic() - self._last_frame_at > self.IDLE_AFTER

                if reopen or not opened:
                    opened = self._open(cfg)
                    if not opened:
                        time.sleep(2)
                        with self._cond:
                            self._reopen = True
                        continue

                img = None
                if frame is not None:
                    if not isinstance(frame, np.ndarray):
                        frame = frame.to_ndarray(format="rgb24")
                    self.input_size = (frame.shape[1], frame.shape[0])
                    img = compose(frame, cfg)
                elif idle:
                    img = placeholder(cfg, self._idle_text)
                    time.sleep(1 / 10)  # placeholder a ~10 fps basta

                if img is not None:
                    try:
                        self.output.send(img)
                        self.sent += 1
                    except Exception as e:
                        self.error = str(e)
                        log.exception("Error enviando frame")
                        with self._cond:
                            self._reopen = True

                now = time.monotonic()
                if now - last_stats >= 1.0:
                    fps = (self.received - last_received) / (now - last_stats)
                    last_stats, last_received = now, self.received
                    if self._on_stats:
                        self._on_stats(
                            {
                                "fps": round(fps, 1),
                                "input": self.input_size,
                                "dropped": self.dropped,
                                "output": f"{cfg.width}x{cfg.height}@{cfg.fps}",
                                "output_name": self.output.name,
                                "error": self.error,
                                "streaming": not idle,
                            }
                        )
        finally:
            self.output.close()
