"""Animated spinner utility for progress indication."""

from __future__ import annotations

import time


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
