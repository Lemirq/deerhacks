"""
pi/capture.py — Webcam frame capture for Neuro-Sync Pi client.

Grabs a single JPEG frame from the USB webcam and returns raw bytes.
That's the entire job of this file. No processing, no analysis — just capture.

The frame gets sent directly to the laptop server as a multipart file upload.
Gemini does all the visual analysis on the laptop side.

Hardware:
  USB webcam plugged into any USB-A port on the Raspberry Pi.
  Detected automatically as /dev/video0 (or video1 if something else is plugged in).

Why not use picamera2?
  USB webcam works on any Pi without enabling the camera interface in raspi-config.
  Lower friction for a hackathon setup. If you're using the official Pi Camera Module,
  see the PICAMERA2 FALLBACK section at the bottom of this file.
"""

import logging
import time
from typing import Optional

import cv2

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

CAMERA_INDEX   = 0      # /dev/video0 — change to 1 if webcam isn't on index 0
FRAME_WIDTH    = 640    # px — enough for Gemini, not so large it slows the upload
FRAME_HEIGHT   = 480    # px
JPEG_QUALITY   = 82     # 0-100. 82 is a good balance of quality vs file size (~35KB)
WARMUP_FRAMES  = 3      # Discard this many frames on first open (camera needs to adjust exposure)


# ─────────────────────────────────────────────
# CAMERA MANAGER
# Keeps the VideoCapture object open across calls so we don't pay
# the ~400ms open/close cost on every loop iteration.
# ─────────────────────────────────────────────

class CameraManager:
    """
    Manages a persistent OpenCV VideoCapture instance.
    
    Stays open for the entire session — opening and closing a camera
    every 3 seconds adds ~400ms of overhead per loop which kills latency.
    
    Includes auto-recovery: if a frame read fails, it closes and
    re-opens the camera rather than crashing the whole session.
    """

    def __init__(self, index: int = CAMERA_INDEX):
        self.index   = index
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_count = 0

    def _open(self):
        """Opens the VideoCapture and configures resolution."""
        logger.info(f"Opening camera at index {self.index}...")

        cap = cv2.VideoCapture(self.index)

        if not cap.isOpened():
            raise RuntimeError(
                f"Could not open camera at index {self.index}. "
                f"Check webcam is plugged in and run: ls /dev/video*"
            )

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer — we want the LATEST frame, not a queued one

        # Warm up — first few frames are often dark/blurry as auto-exposure adjusts
        logger.info(f"Warming up camera ({WARMUP_FRAMES} frames)...")
        for _ in range(WARMUP_FRAMES):
            cap.read()
            time.sleep(0.05)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(f"Camera ready: {actual_w}x{actual_h}")

        self._cap = cap

    def _close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Camera released.")

    def capture_jpeg(self) -> bytes:
        """
        Captures one frame and returns it as JPEG bytes.
        
        Auto-recovers if the camera disconnects mid-session by
        attempting to re-open once before raising an error.
        
        Returns:
            bytes: Raw JPEG-encoded frame ready to POST to the server.
        
        Raises:
            RuntimeError: If camera cannot be opened or frame read fails twice.
        """
        if self._cap is None:
            self._open()

        ret, frame = self._cap.read()

        # If read failed, try once to recover by re-opening
        if not ret or frame is None:
            logger.warning("Frame read failed — attempting camera recovery...")
            self._close()
            time.sleep(0.5)
            self._open()

            ret, frame = self._cap.read()
            if not ret or frame is None:
                raise RuntimeError(
                    "Camera read failed after recovery attempt. "
                    "Check webcam connection."
                )

        self._frame_count += 1

        # Encode to JPEG
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        success, buffer = cv2.imencode(".jpg", frame, encode_params)

        if not success:
            raise RuntimeError("cv2.imencode failed — could not encode frame to JPEG.")

        jpeg_bytes = buffer.tobytes()

        logger.debug(
            f"Frame #{self._frame_count} captured: "
            f"{frame.shape[1]}x{frame.shape[0]} → {len(jpeg_bytes):,} bytes JPEG"
        )

        return jpeg_bytes

    def release(self):
        """Call this on shutdown to cleanly release the camera."""
        self._close()


# ─────────────────────────────────────────────
# MODULE-LEVEL SINGLETON
# pi/main.py imports `capture_jpeg` directly — no need to
# instantiate CameraManager manually.
# ─────────────────────────────────────────────

_manager: Optional[CameraManager] = None

def get_manager() -> CameraManager:
    global _manager
    if _manager is None:
        _manager = CameraManager(index=CAMERA_INDEX)
    return _manager

def capture_jpeg() -> bytes:
    """
    Public API for this module.
    Call this from pi/main.py to get a JPEG frame.
    
    Returns raw JPEG bytes.
    """
    return get_manager().capture_jpeg()

def release_camera():
    """Call on shutdown to release the webcam."""
    global _manager
    if _manager is not None:
        _manager.release()
        _manager = None


# ─────────────────────────────────────────────
# PICAMERA2 FALLBACK
# If you're using the official Raspberry Pi Camera Module instead
# of a USB webcam, replace capture_jpeg() with this version:
#
# from picamera2 import Picamera2
# import io
#
# _picam = None
#
# def capture_jpeg() -> bytes:
#     global _picam
#     if _picam is None:
#         _picam = Picamera2()
#         config = _picam.create_still_configuration(
#             main={"size": (640, 480), "format": "RGB888"}
#         )
#         _picam.configure(config)
#         _picam.start()
#         time.sleep(0.5)  # Let exposure settle
#
#     buf = io.BytesIO()
#     _picam.capture_file(buf, format="jpeg")
#     return buf.getvalue()
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# QUICK TEST
# Run directly to verify camera is working:
#   python3 capture.py
# Saves a test.jpg you can view on your laptop via SCP.
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    print("Testing camera capture...")

    try:
        jpeg = capture_jpeg()
        with open("test_capture.jpg", "wb") as f:
            f.write(jpeg)
        print(f"✓ Captured frame: {len(jpeg):,} bytes")
        print(f"  Saved to test_capture.jpg")
        print(f"  View it: scp pi@neurosync.local:~/neuro-sync/pi/test_capture.jpg ~/Desktop/")
    except RuntimeError as e:
        print(f"✗ Camera error: {e}")
    finally:
        release_camera()
