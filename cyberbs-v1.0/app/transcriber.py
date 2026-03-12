"""
Whisper-based audio chunker/transcriber.
Yields (chunk_index, start_sec, end_sec, transcript) tuples.
"""
import torch
import whisper
import numpy as np
from typing import Iterator

SAMPLE_RATE = 16000
CHUNK_SECONDS = 15  # process this many seconds at a time
_USE_GPU = torch.cuda.is_available()
_USE_MPS = (not _USE_GPU) and torch.backends.mps.is_available()


class AudioTranscriber:
    def __init__(self, model_size: str = "base"):
        # Whisper has limited MPS support, so keep it on CPU for stability
        device = "cuda" if _USE_GPU else "cpu"
        self.model = whisper.load_model(model_size, device=device)
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
        try:
            audio = whisper.load_audio(audio_path)
        except FileNotFoundError:
            raise RuntimeError(
                "ffmpeg not found. Whisper requires ffmpeg to decode audio files.\n"
                "  Windows: download from https://ffmpeg.org/download.html and add to PATH\n"
                "  macOS:   brew install ffmpeg\n"
                "  Linux:   sudo apt install ffmpeg"
            ) from None
        total_samples = len(audio)
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

            # Pad short final chunks so Whisper doesn't complain
            if len(chunk) < chunk_samples:
                chunk = np.pad(chunk, (0, chunk_samples - len(chunk)))

            result = self.model.transcribe(chunk, fp16=_USE_GPU)
            text = result["text"].strip()
            yield (i, start / SAMPLE_RATE, end / SAMPLE_RATE, text)
            i += 1
