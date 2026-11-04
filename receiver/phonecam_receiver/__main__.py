import argparse
import logging
import sys

from .app import DEFAULT_PORT, ReceiverApp, load_config
from dataclasses import replace


def main() -> None:
    p = argparse.ArgumentParser(prog="phonecam", description="Receptor PhoneCam: usa tu teléfono como webcam.")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--name", help="Nombre que verá el teléfono (por defecto, el de la PC)")
    p.add_argument("--output", choices=["virtualcam", "preview", "null"], default="virtualcam")
    p.add_argument("--backend", help="Backend de pyvirtualcam (obs, unitycapture, v4l2loopback)")
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--fps", type=int)
    p.add_argument("--fill", action="store_true", help="Recortar para llenar en lugar de barras negras")
    p.add_argument("--mirror", action="store_true")
    p.add_argument("--no-gui", action="store_true", help="Solo consola")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    if not a.no_gui:  # en el .exe no hay consola: guardar también en archivo
        from .app import config_path
        log_file = config_path().with_name("phonecam.log")
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(fh)
    for noisy in ("aioice", "aiortc", "zeroconf"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    cfg = load_config()
    overrides = {k: v for k, v in (("width", a.width), ("height", a.height), ("fps", a.fps)) if v}
    if a.fill:
        overrides["mode"] = "fill"
    if a.mirror:
        overrides["mirror"] = True
    cfg = replace(cfg, **overrides)

    app = ReceiverApp(cfg, a.output, a.port, a.name, a.backend)
    if a.no_gui:
        app.run_forever()
        return
    try:
        from . import gui
    except ImportError as e:
        print(f"GUI no disponible ({e}); usando consola", file=sys.stderr)
        app.run_forever()
        return
    gui.run(app)


if __name__ == "__main__":
    main()
