"""
Real-time microphone transcriber using sounddevice + Whisper.

Audio is recorded in a background thread and accumulated into chunk-sized
buffers so Whisper transcription never drops frames while the main thread
is busy with inference.

Requires: pip install sounddevice
macOS:    brew install portaudio
Linux:    sudo apt install libportaudio2
"""
import platform
import queue
import threading
from typing import Iterator

import numpy as np
import torch
import whisper

SAMPLE_RATE = 16_000


def _portaudio_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "  macOS:  brew install portaudio"
    if system == "Linux":
        return "  Linux:  sudo apt install libportaudio2"
    return "  Install the PortAudio library for your OS, then retry."


def _check_sounddevice():
    try:
        import sounddevice as sd
        # Probe device list — raises if portaudio is missing
        sd.query_devices()
        return sd
    except ImportError:
        raise RuntimeError(
            "sounddevice is not installed.\n"
            "  Run:    pip install sounddevice\n"
            + _portaudio_hint()
        )
    except OSError as e:
        if "PortAudio" in str(e):
            raise RuntimeError(
                "PortAudio library not found. Install it first, then retry.\n"
                + _portaudio_hint()
            )
        raise RuntimeError(f"sounddevice failed to initialise: {e}")
    except Exception as e:
        raise RuntimeError(f"sounddevice failed to initialise: {e}")


class MicTranscriber:
    def __init__(self, model_size: str = "base", chunk_seconds: int = 15):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = whisper.load_model(model_size, device=device)
        self.chunk_seconds = chunk_seconds
        self._frame_queue: queue.Queue = queue.Queue()
        self._chunk_queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._error: Exception | None = None   # recording thread sets this on crash
        self._recording_started = False

    def start(self):
        """Begin recording immediately. Call this as early as possible so audio
        accumulates while the UI and other setup code runs."""
        if not self._recording_started:
            self._recording_started = True
            t = threading.Thread(target=self._recording_thread, daemon=True)
            t.start()

    def stop(self):
        self._stop.set()

    def _audio_callback(self, indata, frames, time_info, status):
        """Called from the sounddevice audio thread for each block of samples."""
        self._frame_queue.put(indata[:, 0].copy())

    def _recording_thread(self):
        """Accumulates mic frames into full chunks and posts them to _chunk_queue."""
        try:
            sd = _check_sounddevice()
            chunk_samples = self.chunk_seconds * SAMPLE_RATE
            buffer = np.empty(0, dtype=np.float32)

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=self._audio_callback,
                blocksize=4096,
            ):
                while not self._stop.is_set():
                    try:
                        frames = self._frame_queue.get(timeout=0.2)
                        buffer = np.concatenate([buffer, frames])
                        while len(buffer) >= chunk_samples:
                            self._chunk_queue.put(buffer[:chunk_samples].copy())
                            buffer = buffer[chunk_samples:]
                    except queue.Empty:
                        continue
        except Exception as exc:
            self._error = exc
            self._stop.set()          # unblock the generator so it can raise

    def transcribe_chunks(
        self, stop_event: threading.Event | None = None
    ) -> Iterator[tuple[int, float, float, str]]:
        """
        Start mic recording and yield transcribed chunks in real time.
        Pass stop_event (e.g. skipper.quit_event) for instant Q-to-quit response.
        Yields: (chunk_idx, start_sec, end_sec, transcript_text)
        """
        self.start()

        use_fp16 = torch.cuda.is_available()
        chunk_idx = 0

        while True:
            # Stop conditions checked first so we raise errors before exiting
            if self._error:
                raise self._error
            if self._stop.is_set():
                break
            if stop_event and stop_event.is_set():
                break

            try:
                audio = self._chunk_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            start = float(chunk_idx * self.chunk_seconds)
            end   = float(start + self.chunk_seconds)

            result = self.model.transcribe(audio, fp16=use_fp16)
            text   = result["text"].strip()

            yield (chunk_idx, start, end, text)
            chunk_idx += 1

        # Final check — error may have arrived right as we exited the loop
        if self._error:
            raise self._error
