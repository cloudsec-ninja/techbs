"""
Skip controller for prerecorded audio playback.
Listens for keypresses in a background thread and signals
the realtime sync loop to fast-forward.
"""
import os
import sys
import select
import threading


class SkipController:
    """Manages skip-ahead requests from user keypresses."""

    def __init__(self):
        self._skip_event = threading.Event()
        self._quit_event = threading.Event()
        self._listener: threading.Thread | None = None

    @property
    def skip_requested(self) -> bool:
        return self._skip_event.is_set()

    @property
    def quit_requested(self) -> bool:
        return self._quit_event.is_set()

    @property
    def quit_event(self) -> threading.Event:
        return self._quit_event

    def consume_skip(self) -> bool:
        """Return True and clear if a skip was pending."""
        if self._skip_event.is_set():
            self._skip_event.clear()
            return True
        return False

    def wait_interruptible(self, timeout: float) -> bool:
        """Sleep up to *timeout* seconds; return True if interrupted by skip/quit."""
        return self._skip_event.wait(timeout) or self._quit_event.is_set()

    def start(self):
        """Start the background keypress listener."""
        self._listener = threading.Thread(target=self._listen, daemon=True)
        self._listener.start()

    def stop(self):
        self._quit_event.set()

    # ── private ──────────────────────────────────────────────
    def _listen(self):
        """Read raw keypresses from stdin (Unix only)."""
        import termios
        import tty

        fd = sys.stdin.fileno()
        try:
            old_settings = termios.tcgetattr(fd)
        except termios.error:
            return  # not a terminal

        try:
            tty.setcbreak(fd)
            while not self._quit_event.is_set():
                if select.select([sys.stdin], [], [], 0.2)[0]:
                    ch = sys.stdin.read(1)
                    if ch in ("s", "S", "n", "N", " "):
                        self._skip_event.set()
                    elif ch in ("q", "Q", "\x03"):  # q or Ctrl-C
                        self._quit_event.set()
                        break
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
