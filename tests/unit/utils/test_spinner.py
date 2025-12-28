"""Tests for spinner animation utility."""

from __future__ import annotations

import time

from pgslice.utils.spinner import SpinnerAnimator


class TestSpinnerAnimator:
    """Tests for SpinnerAnimator class."""

    def test_init_default_interval(self) -> None:
        """Should initialize with default update interval."""
        spinner = SpinnerAnimator()
        assert spinner.update_interval == 0.1

    def test_init_custom_interval(self) -> None:
        """Should initialize with custom update interval."""
        spinner = SpinnerAnimator(update_interval=0.05)
        assert spinner.update_interval == 0.05

    def test_get_frame_returns_valid_character(self) -> None:
        """Should return a valid Braille spinner character."""
        spinner = SpinnerAnimator()
        frame = spinner.get_frame()
        assert frame in SpinnerAnimator.FRAMES

    def test_get_frame_starts_at_first_frame(self) -> None:
        """Should start at the first frame."""
        spinner = SpinnerAnimator()
        assert spinner.get_frame() == SpinnerAnimator.FRAMES[0]

    def test_get_frame_advances_after_interval(self) -> None:
        """Should advance to next frame after update interval."""
        spinner = SpinnerAnimator(update_interval=0.01)  # 10ms for fast test
        first_frame = spinner.get_frame()

        # Wait for interval to pass
        time.sleep(0.02)  # 20ms to ensure we've passed the interval

        second_frame = spinner.get_frame()
        assert second_frame != first_frame
        assert second_frame == SpinnerAnimator.FRAMES[1]

    def test_get_frame_does_not_advance_before_interval(self) -> None:
        """Should not advance before update interval."""
        spinner = SpinnerAnimator(update_interval=1.0)  # 1 second
        first_frame = spinner.get_frame()

        # Call immediately without waiting
        second_frame = spinner.get_frame()

        assert second_frame == first_frame

    def test_get_frame_cycles_through_all_frames(self) -> None:
        """Should cycle through all frames and wrap around."""
        spinner = SpinnerAnimator(update_interval=0.01)

        # Get first frame
        frames_seen = [spinner.get_frame()]

        # Advance through all frames + a few more to test wrapping
        for _ in range(len(SpinnerAnimator.FRAMES) + 2):
            time.sleep(0.015)  # Wait for interval
            frames_seen.append(spinner.get_frame())

        # Should have cycled through all frames
        assert SpinnerAnimator.FRAMES[0] in frames_seen
        assert SpinnerAnimator.FRAMES[-1] in frames_seen
        # Should have wrapped around (first frame appears at start and after full cycle)
        assert frames_seen.count(SpinnerAnimator.FRAMES[0]) >= 2

    def test_reset_returns_to_first_frame(self) -> None:
        """Should reset to first frame."""
        spinner = SpinnerAnimator(update_interval=0.01)

        # Advance a few frames
        for _ in range(3):
            time.sleep(0.015)
            spinner.get_frame()

        # Reset
        spinner.reset()

        # Should be back at first frame
        assert spinner.get_frame() == SpinnerAnimator.FRAMES[0]

    def test_reset_updates_last_update_time(self) -> None:
        """Should update last update time on reset."""
        spinner = SpinnerAnimator(update_interval=0.01)

        # Advance one frame
        time.sleep(0.015)
        spinner.get_frame()

        # Reset and immediately call get_frame
        spinner.reset()
        frame_after_reset = spinner.get_frame()

        # Should still be at first frame (not advanced immediately)
        assert frame_after_reset == SpinnerAnimator.FRAMES[0]

    def test_frames_constant_contains_braille_patterns(self) -> None:
        """Should have 10 Braille pattern frames."""
        assert len(SpinnerAnimator.FRAMES) == 10
        expected_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        assert expected_frames == SpinnerAnimator.FRAMES

    def test_high_frequency_calls_respect_interval(self) -> None:
        """Should respect update interval even with high frequency calls."""
        spinner = SpinnerAnimator(update_interval=0.1)

        # Call get_frame many times rapidly
        frames = []
        for _ in range(50):
            frames.append(spinner.get_frame())
            time.sleep(0.001)  # 1ms between calls

        # Should have stayed on first frame for most calls
        # (50ms total, so only about half the interval)
        assert frames.count(SpinnerAnimator.FRAMES[0]) > 40
