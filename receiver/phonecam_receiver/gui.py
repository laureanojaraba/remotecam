"""Ventana sencilla (tkinter): estado, QR para conectar y ajustes de salida."""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import ttk

import qrcode
from PIL import ImageTk

from .app import ReceiverApp, save_config

RESOLUTIONS = {"1280x720 (HD)": (1280, 720), "1920x1080 (Full HD)": (1920, 1080),
               "2560x1440 (2K)": (2560, 1440), "3840x2160 (4K)": (3840, 2160)}
FPS = [24, 30, 60]


def run(app: ReceiverApp) -> None:
    root = tk.Tk()
    root.title("PhoneCam")
    root.resizable(False, False)
    pad = {"padx": 12, "pady": 4}

    status = tk.StringVar(value="Iniciando...")
    detail = tk.StringVar(value="")
    address = tk.StringVar(value="")

    ttk.Label(root, text="PhoneCam", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, **pad)
    ttk.Label(root, textvariable=status, font=("Segoe UI", 11)).grid(row=1, column=0, columnspan=2, **pad)
    ttk.Label(root, textvariable=detail, foreground="#666").grid(row=2, column=0, columnspan=2, **pad)

    qr_label = ttk.Label(root)
    qr_label.grid(row=3, column=0, columnspan=2, padx=12, pady=8)
    ttk.Label(root, text="Abre la app en el teléfono: la PC aparece sola.\n"
                         "Si no, toca \"Escanear QR\" o escribe la dirección:",
              justify="center").grid(row=4, column=0, columnspan=2, **pad)
    ttk.Label(root, textvariable=address, font=("Consolas", 12)).grid(row=5, column=0, columnspan=2, **pad)

    # --- ajustes
    cfg = app.pipeline.cfg
    frame = ttk.LabelFrame(root, text="Salida de la cámara virtual")
    frame.grid(row=6, column=0, columnspan=2, padx=12, pady=10, sticky="ew")

    res_names = list(RESOLUTIONS)
    current_res = next((k for k, v in RESOLUTIONS.items() if v == (cfg.width, cfg.height)), res_names[1])
    res_var = tk.StringVar(value=current_res)
    fps_var = tk.IntVar(value=cfg.fps if cfg.fps in FPS else 30)
    mode_var = tk.StringVar(value=cfg.mode)
    mirror_var = tk.BooleanVar(value=cfg.mirror)

    def apply(*_):
        w, h = RESOLUTIONS[res_var.get()]
        app.pipeline.set_config(width=w, height=h, fps=int(fps_var.get()),
                                mode=mode_var.get(), mirror=bool(mirror_var.get()))
        save_config(app.pipeline.cfg)

    ttk.Label(frame, text="Resolución").grid(row=0, column=0, sticky="w", padx=8, pady=4)
    ttk.Combobox(frame, textvariable=res_var, values=res_names, state="readonly", width=20).grid(row=0, column=1, padx=8)
    ttk.Label(frame, text="FPS").grid(row=1, column=0, sticky="w", padx=8, pady=4)
    ttk.Combobox(frame, textvariable=fps_var, values=FPS, state="readonly", width=20).grid(row=1, column=1, padx=8)
    ttk.Label(frame, text="Ajuste").grid(row=2, column=0, sticky="w", padx=8, pady=4)
    modes = ttk.Frame(frame)
    modes.grid(row=2, column=1, sticky="w")
    ttk.Radiobutton(modes, text="Completa (barras)", value="fit", variable=mode_var, command=apply).pack(side="left")
    ttk.Radiobutton(modes, text="Recortar", value="fill", variable=mode_var, command=apply).pack(side="left")
    ttk.Checkbutton(frame, text="Espejo horizontal", variable=mirror_var, command=apply).grid(
        row=3, column=1, sticky="w", padx=8, pady=4)
    res_var.trace_add("write", apply)
    fps_var.trace_add("write", apply)

    ttk.Label(root, text="Nota: cambiar resolución/FPS reinicia la cámara virtual;\n"
                         "algunas apps (Zoom/Meet) necesitan volver a seleccionarla.",
              foreground="#888", justify="center").grid(row=7, column=0, columnspan=2, **pad)

    def show_qr(payload: str) -> None:
        img = qrcode.make(payload, box_size=6, border=2).get_image().convert("RGB")
        photo = ImageTk.PhotoImage(img)
        qr_label.configure(image=photo)
        qr_label.image = photo  # evitar que el GC la borre

    def poll() -> None:
        try:
            while True:
                ev = app.events.get_nowait()
                kind = ev["event"]
                if kind == "ready":
                    status.set("Listo — esperando teléfono")
                    address.set("\n".join(f"{ip}:{ev['port']}" for ip in ev["ips"]) or "(sin red)")
                    show_qr(app.announcer.qr_payload())
                elif kind == "connecting":
                    status.set(f"Conectando con {ev['device']}...")
                elif kind == "state" and ev["state"] == "connected":
                    status.set(f"Conectado: {ev['device']}")
                elif kind == "disconnected":
                    status.set("Teléfono desconectado — esperando")
                    detail.set("")
                elif kind == "fatal":
                    status.set("Error al iniciar")
                    detail.set(ev["error"])
                elif kind == "stats":
                    if ev["error"]:
                        detail.set(f"⚠ Cámara virtual: {ev['error'][:90]}")
                    elif ev["streaming"] and ev["input"]:
                        w, h = ev["input"]
                        detail.set(f"Entrada {w}x{h} · {ev['fps']} fps → salida {ev['output']}")
                    else:
                        detail.set(f"Salida: {ev['output_name']}")
        except queue.Empty:
            pass
        root.after(200, poll)

    def on_close() -> None:
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    app.start_background()
    poll()
    try:
        root.mainloop()
    finally:
        app.shutdown()
