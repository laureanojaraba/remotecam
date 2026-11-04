"""Simula el teléfono: envía un patrón de prueba por WebRTC al receptor.

Uso: python tools/fake_phone.py --host 127.0.0.1 --seconds 10 [--width 1920 --height 1080]
"""

import argparse
import asyncio
import fractions
import json
import time

import aiohttp
import numpy as np
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame


class Pattern(VideoStreamTrack):
    def __init__(self, w, h, fps):
        super().__init__()
        self.w, self.h, self.fps = w, h, fps
        self.n = 0
        self.t0 = None

    async def recv(self):
        if self.t0 is None:
            self.t0 = time.monotonic()
        target = self.t0 + self.n / self.fps
        await asyncio.sleep(max(0, target - time.monotonic()))
        img = np.zeros((self.h, self.w, 3), np.uint8)
        x = (self.n * 8) % self.w
        img[:, x : x + 40] = (255, 80, 0)
        img[: self.h // 4, :, 1] = 200
        frame = VideoFrame.from_ndarray(img, format="rgb24")
        frame.pts = self.n
        frame.time_base = fractions.Fraction(1, self.fps)
        self.n += 1
        return frame


async def main(a):
    async with aiohttp.ClientSession() as s:
        info = await (await s.get(f"http://{a.host}:{a.port}/info")).json()
        print("info:", info)
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        pc.addTrack(Pattern(a.width, a.height, a.fps))
        await pc.setLocalDescription(await pc.createOffer())
        async with s.ws_connect(f"ws://{a.host}:{a.port}/ws") as ws:
            await ws.send_json({"type": "offer", "sdp": pc.localDescription.sdp, "device": "FakePhone"})
            msg = json.loads((await ws.receive()).data)
            await pc.setRemoteDescription(RTCSessionDescription(msg["sdp"], "answer"))
            try:  # seguir leyendo para responder los pings del servidor
                await asyncio.wait_for(ws.receive(), a.seconds)
            except asyncio.TimeoutError:
                pass
            print("estado:", pc.connectionState)
            await ws.send_json({"type": "bye"})
        await pc.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--seconds", type=float, default=8)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    asyncio.run(main(p.parse_args()))
