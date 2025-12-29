"""Animated spinner utility for progress indication."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class SpinnerAnimator:
    """
    Animated spinner using Braille patterns.

    Rotates through spinner frames at a fixed rate (time-based)
    to provide smooth animation regardless of callback frequency.
    """

    # Braille spinner frames for smooth rotation
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, update_interval: float = 0.1) -> None:
        """
        Initialize spinner animator.

        Args:
            update_interval: Minimum time (in seconds) between frame updates.
                           Default: 0.1 seconds (100ms) for smooth animation.
        """
        self.update_interval = update_interval
        self._current_idx = 0
        self._last_update = time.time()

    def get_frame(self) -> str:
        """
        Get current spinner frame and advance if enough time has passed.

        Returns:
            Current spinner character
        """
        current_time = time.time()
        if current_time - self._last_update >= self.update_interval:
            self._current_idx = (self._current_idx + 1) % len(self.FRAMES)
            self._last_update = current_time

        return self.FRAMES[self._current_idx]

    def reset(self) -> None:
        """Reset spinner to initial state."""
        self._current_idx = 0
        self._last_update = time.time()


@contextmanager
def animated_spinner(
    spinner: SpinnerAnimator,
    update_fn: Callable[[str], None],
    base_text: str,
    interval: float = 0.1,
) -> Iterator[None]:
    """
    Context manager that animates spinner in background thread.

    Args:
        spinner: SpinnerAnimator instance
        update_fn: Function to call with updated description (e.g., pbar.set_description)
        base_text: Base description text (spinner appended)
        interval: Update interval in seconds

    Usage:
        with animated_spinner(spinner, pbar.set_description, "Sorting dependencies"):
            sorter.sort(records)  # Spinner animates during this
    """
    stop_event = threading.Event()

    def animate() -> None:
        while not stop_event.is_set():
            update_fn(f"{base_text} {spinner.get_frame()}")
            stop_event.wait(interval)

    thread = threading.Thread(target=animate, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=0.5)
        update_fn(f"{base_text} ✓")
