from __future__ import annotations

from typing import Callable, Optional


class TuneInput:
    """Base class for physical (or virtual) tuning input devices."""

    def start(self, tune: Callable[[float], None]) -> None:
        """Register the tune callback and begin listening for input events."""

    def stop(self) -> None:
        """Stop listening and release hardware resources."""


class GpioButtonInput(TuneInput):
    """Two push-buttons wired to GPIO — one steps down, one steps up."""

    def __init__(self, pin_down: int, pin_up: int, step: float, bounce_time: float = 0.05):
        self.pin_down = pin_down
        self.pin_up = pin_up
        self.step = step
        self.bounce_time = bounce_time
        self._btn_down: Optional[object] = None
        self._btn_up: Optional[object] = None

    def start(self, tune: Callable[[float], None]) -> None:
        from gpiozero import Button  # lazy import — no crash on non-Pi
        self._btn_down = Button(self.pin_down, pull_up=True, bounce_time=self.bounce_time)
        self._btn_up = Button(self.pin_up, pull_up=True, bounce_time=self.bounce_time)
        self._btn_down.when_pressed = lambda: tune(-self.step)
        self._btn_up.when_pressed = lambda: tune(+self.step)

    def stop(self) -> None:
        for b in (self._btn_down, self._btn_up):
            if b:
                b.close()
        self._btn_down = None
        self._btn_up = None
