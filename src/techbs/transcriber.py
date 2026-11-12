"""
Whisper-based audio chunker/transcriber (faster-whisper).
Yields (chunk_index, start_sec, end_sec, transcript) tuples.
"""
import numpy as np
from typing import Iterator

from .whisper_engine import SAMPLE_RATE, load_audio, load_whisper, transcribe_array

CHUNK_SECONDS = 15  # process this many seconds at a time


class AudioTranscriber:
    def __init__(self, model_name: str):
        self.model = load_whisper(model_name)
        self.device = self.model.techbs_device
        self.duration: float | None = None  # seconds; known once the audio is decoded
        self._skip_to_index: int | None = None

    def skip_to(self, chunk_index: int):
        """Request the generator to jump ahead to *chunk_index* on its next iteration."""
        self._skip_to_index = chunk_index

    def transcribe_chunks(
        self, audio_path: str, chunk_seconds: int = CHUNK_SECONDS
    ) -> Iterator[tuple[int, float, float, str]]:
        """
        Load an audio file and yield transcribed chunks in order.
        Yields: (chunk_idx, start_sec, end_sec, transcript_text)
        """
        audio = load_audio(audio_path)
        total_samples = len(audio)
        self.duration = total_samples / SAMPLE_RATE
        chunk_samples = chunk_seconds * SAMPLE_RATE
        num_chunks = max(1, (total_samples + chunk_samples - 1) // chunk_samples)

        i = 0
        while i < num_chunks:
            # Check if we've been asked to skip ahead
            if self._skip_to_index is not None and self._skip_to_index > i:
                i = self._skip_to_index
                self._skip_to_index = None
                if i >= num_chunks:
                    return
                continue

            self._skip_to_index = None

            start = i * chunk_samples
            end = min(start + chunk_samples, total_samples)
            chunk = audio[start:end]

            # Pad short final chunks to a full window
            if len(chunk) < chunk_samples:
                chunk = np.pad(chunk, (0, chunk_samples - len(chunk)))

            text = transcribe_array(self.model, chunk)
            yield (i, start / SAMPLE_RATE, end / SAMPLE_RATE, text)
            i += 1
