"""
CORE_ENGINE/MEDIA_RECORDER.PY
Purpose: REAL screen recording for the Kalandra overlay.

This replaces the old placeholder that wrote the literal text
"Placeholder video clip data" into a .mp4 file (which is why it never played).

It captures the *same primary screen* the snapshot tool grabs, writes a real,
playable H.264/MP4 file using OpenCV's VideoWriter, and runs the capture loop on
a background thread so the PyQt UI never freezes.

Optionally it also records the microphone to a sidecar .wav so the recording can
be transcribed afterwards (see voice_engine.transcribe_file).

All heavy dependencies are imported lazily and guarded: if a library is missing
the recorder reports AVAILABLE = False with a helpful reason instead of crashing
the whole overlay.

Install:
    pip install mss opencv-python numpy
    pip install sounddevice soundfile      # (optional) for microphone audio
"""

import os
import time
import threading
import wave
from datetime import datetime

# ---- Guarded optional imports -------------------------------------------------
_IMPORT_ERRORS = []
try:
    import numpy as np
except Exception as e:  # pragma: no cover
    np = None
    _IMPORT_ERRORS.append(f"numpy ({e})")

try:
    import mss
except Exception as e:  # pragma: no cover
    mss = None
    _IMPORT_ERRORS.append(f"mss ({e})")

try:
    import cv2
except Exception as e:  # pragma: no cover
    cv2 = None
    _IMPORT_ERRORS.append(f"opencv-python ({e})")

# Audio is fully optional.
try:
    import sounddevice as _sd
except Exception:
    _sd = None


VIDEO_AVAILABLE = (np is not None) and (mss is not None) and (cv2 is not None)
AUDIO_AVAILABLE = (_sd is not None) and (np is not None)


class ScreenRecorder:
    """Threaded screen recorder producing a real MP4 (and optional WAV audio)."""

    def __init__(self, output_dir="data_engine/clips", fps=15,
                 monitor_index=1, capture_audio=True, audio_samplerate=44100):
        self.output_dir = output_dir
        self.fps = max(1, int(fps))
        # mss.monitors[0] = the union of all monitors, [1] = the primary monitor.
        self.monitor_index = monitor_index
        self.capture_audio = bool(capture_audio and AUDIO_AVAILABLE)
        self.audio_samplerate = audio_samplerate

        self._thread = None
        self._stop_flag = threading.Event()
        self._is_recording = False

        self._video_path = None
        self._audio_path = None
        self._audio_frames = []
        self._audio_stream = None

    # -- public API ------------------------------------------------------------
    @property
    def is_recording(self):
        return self._is_recording

    def availability_message(self):
        if VIDEO_AVAILABLE:
            return "Screen recording ready."
        return ("Screen recording needs extra libraries. Run:\n"
                "    pip install mss opencv-python numpy\n\n"
                f"Missing: {', '.join(_IMPORT_ERRORS) or 'unknown'}")

    def start(self):
        """Begin recording. Returns True if it actually started."""
        if not VIDEO_AVAILABLE:
            return False
        if self._is_recording:
            return False

        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._video_path = os.path.join(self.output_dir, f"clip_{timestamp}.mp4")
        self._audio_path = os.path.join(self.output_dir, f"clip_{timestamp}.wav")
        self._stop_flag.clear()
        self._audio_frames = []

        # Start audio capture first (best-effort).
        if self.capture_audio:
            try:
                self._audio_stream = _sd.InputStream(
                    samplerate=self.audio_samplerate,
                    channels=1,
                    dtype="int16",
                    callback=self._audio_callback,
                )
                self._audio_stream.start()
            except Exception:
                # Microphone may be busy/unavailable -> record video only.
                self._audio_stream = None
                self.capture_audio = False

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._is_recording = True
        self._thread.start()
        return True

    def stop(self):
        """Stop recording and finalize files.

        Returns a dict: {"video": path|None, "audio": path|None}.
        """
        if not self._is_recording:
            return {"video": None, "audio": None}

        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._is_recording = False

        audio_out = None
        if self._audio_stream is not None:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
            except Exception:
                pass
            audio_out = self._write_wav()

        return {"video": self._video_path, "audio": audio_out}

    # -- internals -------------------------------------------------------------
    def _audio_callback(self, indata, frames, time_info, status):
        # Copy because the buffer is reused by PortAudio.
        self._audio_frames.append(indata.copy())

    def _write_wav(self):
        if not self._audio_frames:
            return None
        try:
            data = np.concatenate(self._audio_frames, axis=0)
            with wave.open(self._audio_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # int16
                wf.setframerate(self.audio_samplerate)
                wf.writeframes(data.tobytes())
            return self._audio_path
        except Exception:
            return None

    def _capture_loop(self):
        """Grab the primary screen at a steady fps and write H.264/MP4 frames."""
        frame_interval = 1.0 / self.fps
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = None

        with mss.mss() as sct:
            # Pick the requested monitor, falling back to primary if needed.
            monitors = sct.monitors
            idx = self.monitor_index if self.monitor_index < len(monitors) else 1
            monitor = monitors[idx]
            width = monitor["width"]
            height = monitor["height"]

            writer = cv2.VideoWriter(self._video_path, fourcc, self.fps, (width, height))
            if not writer.isOpened():
                # Codec problem -> try a more universally available one.
                fourcc = cv2.VideoWriter_fourcc(*"XVID")
                self._video_path = os.path.splitext(self._video_path)[0] + ".avi"
                writer = cv2.VideoWriter(self._video_path, fourcc, self.fps, (width, height))

            next_t = time.time()
            while not self._stop_flag.is_set():
                shot = sct.grab(monitor)
                # mss returns BGRA; OpenCV wants BGR.
                frame = np.asarray(shot)[:, :, :3]
                writer.write(frame)

                next_t += frame_interval
                sleep_for = next_t - time.time()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                else:
                    # We're behind; reset cadence so we don't spiral.
                    next_t = time.time()

        if writer is not None:
            writer.release()


# Interactive self-test (records 3 seconds of your screen).
if __name__ == "__main__":
    print("media_recorder availability:")
    print(f"  video: {VIDEO_AVAILABLE}  audio: {AUDIO_AVAILABLE}")
    rec = ScreenRecorder(output_dir="data_engine/clips", fps=12)
    if not VIDEO_AVAILABLE:
        print(rec.availability_message())
    else:
        print("Recording 3 seconds...")
        rec.start()
        time.sleep(3)
        out = rec.stop()
        print(f"Saved: {out}")
