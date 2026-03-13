from __future__ import annotations

import threading
import time
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


class RgbEncoderInput(TuneInput):
    """Pimoroni RGB Encoder Breakout connected via I2C (addr 0x0F).

    Each detent of the encoder fires tune(±step).  If interrupt_pin is given
    (the Pi GPIO pin wired to the breakout's INT header), interrupts are used;
    otherwise the encoder is polled at poll_hz.
    """

    # Encoder breakout pin assignments (fixed on the hardware)
    _ENC_A = 12
    _ENC_B = 3
    _ENC_C = 11

    def __init__(
        self,
        step: float,
        i2c_addr: int = 0x0F,
        interrupt_pin: Optional[int] = None,
        poll_hz: float = 30.0,
    ):
        self.step = step
        self.i2c_addr = i2c_addr
        self.interrupt_pin = interrupt_pin
        self._poll_interval = 1.0 / poll_hz
        self._tune: Optional[Callable[[float], None]] = None
        self._ioe: Optional[object] = None
        self._last_count: int = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self, tune: Callable[[float], None]) -> None:
        import ioexpander as io  # lazy — no crash on non-Pi

        self._tune = tune

        if self.interrupt_pin is not None:
            self._ioe = io.IOE(i2c_addr=self.i2c_addr, interrupt_pin=self.interrupt_pin)
            self._ioe.enable_interrupt_out(pin_swap=True)
        else:
            self._ioe = io.IOE(i2c_addr=self.i2c_addr)

        self._ioe.setup_rotary_encoder(1, self._ENC_A, self._ENC_B, pin_c=self._ENC_C)
        self._last_count = self._ioe.read_rotary_encoder(1)

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        ioe = self._ioe
        use_interrupt = self.interrupt_pin is not None

        while self._running:
            if not use_interrupt or ioe.get_interrupt():
                count = ioe.read_rotary_encoder(1)
                if use_interrupt:
                    ioe.clear_interrupt()
                delta = count - self._last_count
                if delta != 0:
                    self._last_count = count
                    self._tune(delta * self.step)
            time.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._ioe = None


class VolumeInput:
    """Base class for physical (or virtual) volume input devices."""

    def start(self, set_volume: Callable[[int], None]) -> None:
        """Register the set_volume callback and begin listening for input events."""

    def stop(self) -> None:
        """Stop listening and release hardware resources."""


class PotentiometerInput(VolumeInput):
    """Pimoroni Potentiometer Breakout connected via I2C (addr 0x0E).

    Reads the potentiometer position and calls set_volume(0–100).
    Polled at poll_hz.
    """

    _POT_PIN = 1

    def __init__(
        self,
        i2c_addr: int = 0x0E,
        poll_hz: float = 10.0,
    ):
        self.i2c_addr = i2c_addr
        self._poll_interval = 1.0 / poll_hz
        self._set_volume: Optional[Callable[[int], None]] = None
        self._ioe: Optional[object] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self, set_volume: Callable[[int], None]) -> None:
        import ioexpander as io  # lazy — no crash on non-Pi

        self._set_volume = set_volume
        self._ioe = io.IOE(i2c_addr=self.i2c_addr)
        self._ioe.set_mode(self._POT_PIN, io.PIN_MODE_ADC)

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        ioe = self._ioe
        while self._running:
            raw = ioe.input(self._POT_PIN)
            vref = ioe.get_adc_vref()
            volume = int((raw / vref) * 100)
            self._set_volume(volume)
            time.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._ioe = None
