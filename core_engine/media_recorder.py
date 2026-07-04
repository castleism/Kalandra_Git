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
                 monitor_index=1, capture_audio=True, audio_samplerate=44100,
                 max_width=1920):
        self.output_dir = output_dir
        self.fps = max(1, int(fps))
        # mss.monitors[0] = the union of all monitors, [1] = the primary monitor.
        self.monitor_index = monitor_index
        self.capture_audio = bool(capture_audio and AUDIO_AVAILABLE)
        self.audio_samplerate = audio_samplerate
        # Frames wider than this are downscaled before encoding. Encoding a
        # 1440p/4K frame in software is the main reason clips used to play
        # like slideshows; 1080p-ish is fast and plenty for build clips.
        self.max_width = max(320, int(max_width)) if max_width else None

        self._thread = None
        self._stop_flag = threading.Event()
        self._is_recording = False

        self._video_path = None
        self._audio_path = None
        self._audio_frames = []
        self._audio_stream = None
        self.last_stats = {}   # filled at stop(): grabbed/written/duplicated/fps

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

        return {"video": self._video_path, "audio": audio_out,
                "stats": dict(self.last_stats)}

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

    @staticmethod
    def plan_writes(elapsed, frame_interval, written, max_burst):
        """How many copies of the CURRENT frame to write so the file's
        timeline stays in step with wall-clock time.

        The old loop wrote each grabbed frame exactly once at whatever rate
        the machine achieved, while the file header promised full fps — so a
        slow grab/encode produced a fast-forwarded slideshow. Duplicating
        the newest frame into every elapsed slot keeps playback speed HONEST
        (1s recorded == 1s played) no matter how slow capture runs.

        Pure math (unit-tested): due = slots elapsed since start; write at
        least 1, at most max_burst (so a system stall can't dump thousands
        of copies)."""
        due = int(elapsed / frame_interval) + 1
        reps = due - int(written)
        if reps < 1:
            reps = 1
        if reps > max_burst:
            reps = max_burst
        return reps

    @staticmethod
    def output_size(width, height, max_width):
        """Downscaled (even-dimension) encode size. Even numbers because
        many codecs refuse odd dimensions."""
        w, h = int(width), int(height)
        if max_width and w > max_width:
            h = int(h * (max_width / float(w)))
            w = int(max_width)
        w -= w % 2
        h -= h % 2
        return max(2, w), max(2, h)

    def _capture_loop(self):
        """Grab the screen as fast as the machine allows and keep the FILE
        timeline honest by duplicating the newest frame into every fps slot
        that has elapsed (see plan_writes). Conversion is cv2.cvtColor (SIMD)
        instead of a numpy slice-copy, and frames above max_width are
        downscaled before encoding — both big per-frame wins."""
        frame_interval = 1.0 / self.fps
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = None
        max_burst = self.fps * 2
        grabbed = written = duplicated = 0
        start = None

        with mss.mss() as sct:
            # Pick the requested monitor, falling back to primary if needed.
            monitors = sct.monitors
            idx = self.monitor_index if self.monitor_index < len(monitors) else 1
            monitor = monitors[idx]
            out_w, out_h = self.output_size(monitor["width"], monitor["height"],
                                            self.max_width)

            writer = cv2.VideoWriter(self._video_path, fourcc, self.fps,
                                     (out_w, out_h))
            if not writer.isOpened():
                # Codec problem -> try a more universally available one.
                fourcc = cv2.VideoWriter_fourcc(*"XVID")
                self._video_path = os.path.splitext(self._video_path)[0] + ".avi"
                writer = cv2.VideoWriter(self._video_path, fourcc, self.fps,
                                         (out_w, out_h))

            start = time.time()
            while not self._stop_flag.is_set():
                shot = sct.grab(monitor)
                grabbed += 1
                # mss returns BGRA; cvtColor is contiguous + SIMD-fast.
                frame = cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)
                if (frame.shape[1], frame.shape[0]) != (out_w, out_h):
                    frame = cv2.resize(frame, (out_w, out_h),
                                       interpolation=cv2.INTER_AREA)
                reps = self.plan_writes(time.time() - start, frame_interval,
                                        written, max_burst)
                for _ in range(reps):
                    writer.write(frame)
                written += reps
                duplicated += reps - 1
                # Sleep only if we're AHEAD of the timeline.
                next_slot = start + written * frame_interval
                sleep_for = next_slot - time.time()
                if sleep_for > 0:
                    time.sleep(sleep_for)

        if writer is not None:
            writer.release()
        wall = (time.time() - start) if start else 0.0
        self.last_stats = {
            "grabbed": grabbed, "written": written, "duplicated": duplicated,
            "capture_fps": round(grabbed / wall, 1) if wall > 0 else 0.0,
            "target_fps": self.fps, "seconds": round(wall, 1),
            "size": f"{out_w}x{out_h}" if grabbed else "",
        }


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
