"""
YOLO object detector. Reads frames from the camera RTSP stream via OpenCV,
runs inference, and fires a callback when a target object is detected.

Model, input size, and device come from the "detection" block in config.json so
they can be tuned without editing code.

Frames are pulled by a dedicated reader thread and inference runs on whatever
the newest one is; see _FrameReader for why that separation is required.

Runs in a thread pool so it doesn't block the asyncio event loop.
"""

import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

# Must be set before cv2 opens any RTSP capture -- otherwise OpenCV's ffmpeg
# backend defaults to UDP, which drops/corrupts frames over longer or switched
# cable runs. hls.py and clipper.py force TCP via their own ffmpeg args; this
# is the equivalent for OpenCV's VideoCapture.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2
from ultralytics import YOLO

log = logging.getLogger(__name__)

# Classes we care about by default. Full list: https://docs.ultralytics.com/datasets/detect/coco/
DEFAULT_CLASSES = {"person", "car", "truck", "motorcycle", "bicycle", "dog", "cat"}

DEFAULT_MODEL = "yolo11m.pt"
DEFAULT_IMGSZ = 1280


def resolve_device(requested: str) -> str:
    """'auto' -> cuda:0 when a GPU is usable, else cpu. Anything else passes through."""
    if requested != "auto":
        return requested
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda:0" if torch.cuda.is_available() else "cpu"


class _FrameReader(threading.Thread):
    """Drains the RTSP stream continuously, keeping only the newest frame.

    Inference is far slower than the stream: roughly 2 fps against a camera
    sending 25. Reading in the same loop back-pressures the decoder, the receive
    buffer overruns, and ffmpeg eventually dies with 'Stream timeout triggered'
    -- observed here after about 90 seconds of continuous capture. Reading in a
    separate thread decouples decode rate from inference rate; surplus frames
    are simply dropped, which is exactly what we want for motion events.

    Owns its own reconnect loop, so the detector never sees a dead capture.
    """

    def __init__(self, url: str, camera_id: str):
        super().__init__(daemon=True, name=f"read_{camera_id}")
        self.url = url
        self.camera_id = camera_id
        self._lock = threading.Lock()
        self._frame = None
        self._count = 0
        self._stop = threading.Event()

    def run(self):
        cap = None
        while not self._stop.is_set():
            if cap is None:
                cap = cv2.VideoCapture(self.url)
                if not cap.isOpened():
                    cap.release()
                    cap = None
                    log.warning("[%s] Could not open RTSP stream, retrying in 5s", self.camera_id)
                    self._stop.wait(5)
                    continue
                log.info("[%s] Detection stream open", self.camera_id)
            ok, frame = cap.read()
            if not ok:
                log.warning("[%s] Stream read failed, reconnecting", self.camera_id)
                cap.release()
                cap = None
                self._stop.wait(2)
                continue
            with self._lock:
                self._frame = frame
                self._count += 1
        if cap is not None:
            cap.release()

    def latest(self):
        """-> (frame, counter). frame is None until the first read lands."""
        with self._lock:
            if self._frame is None:
                return None, self._count
            return self._frame.copy(), self._count

    def stop(self):
        self._stop.set()


class Detector:
    def __init__(self, camera: dict, config: dict, on_detection: Callable, tracker=None):
        det = config.get("detection", {})
        self.camera = camera
        self.on_detection = on_detection
        self.tracker = tracker  # ZoneTracker, or None to skip zone logging
        self.confidence = det.get("confidence", 0.5)
        self.frame_skip = det.get("frame_skip", 5)  # run inference every N frames
        self.cooldown = config["recording"]["motion_cooldown_seconds"]
        self.target_classes = set(det.get("classes", DEFAULT_CLASSES))
        self.model_name = det.get("model", DEFAULT_MODEL)
        self.imgsz = det.get("imgsz", DEFAULT_IMGSZ)
        self.device = resolve_device(det.get("device", "auto"))
        self._model: YOLO | None = None
        self._reader: _FrameReader | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"det_{camera['id']}")

    def _rtsp_url(self) -> str:
        c = self.camera
        return f"rtsp://{c['username']}:{c['password']}@{c['ip']}:{c['rtsp_port']}{c['rtsp_path']}"

    def _load_model(self):
        cam_id = self.camera["id"]
        log.info(
            "[%s] Loading model=%s imgsz=%s device=%s",
            cam_id, self.model_name, self.imgsz, self.device,
        )
        self._model = YOLO(self.model_name)
        self._model.to(self.device)
        if self.device == "cpu":
            # Easy to miss otherwise: a broken CUDA install silently falls back
            # here and inference goes from ~ms to ~100ms with no other symptom.
            log.warning("[%s] Running inference on CPU -- expect much slower detection", cam_id)

    def _run(self):
        """Detection loop -- runs in the thread pool, fed by the reader thread."""
        self._load_model()
        self._reader = _FrameReader(self._rtsp_url(), self.camera["id"])
        self._reader.start()

        last_trigger = 0.0
        last_count = -1

        try:
            while True:
                frame, count = self._reader.latest()
                # Wait for a frame at least frame_skip further on, so the same
                # image is never run twice and the configured spacing is kept.
                if frame is None or count - last_count < self.frame_skip:
                    time.sleep(0.05)
                    continue
                last_count = count

                results = self._model(
                    frame, imgsz=self.imgsz, device=self.device, verbose=False
                )
                detected = set()
                people = []
                height, width = frame.shape[:2]
                for box in results[0].boxes:
                    conf = float(box.conf[0])
                    cls = self._model.names[int(box.cls[0])]
                    if conf < self.confidence or cls not in self.target_classes:
                        continue
                    detected.add(cls)
                    if cls == "person":
                        x1, _, x2, y2 = (float(v) for v in box.xyxy[0])
                        # Bottom-centre of the box = feet on the floor plane.
                        people.append(((x1 + x2) / 2 / width, y2 / height))

                # Runs on every inference frame, empty list included -- an empty
                # frame is what starts the vanish timer.
                if self.tracker:
                    self.tracker.update(people)

                if detected:
                    now = time.time()
                    if now - last_trigger >= self.cooldown:
                        last_trigger = now
                        asyncio.run_coroutine_threadsafe(
                            self.on_detection(self.camera, sorted(detected)),
                            self._loop,
                        )
        finally:
            self._reader.stop()

    async def start(self):
        self._loop = asyncio.get_event_loop()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._run)
