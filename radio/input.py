from __future__ import annotations

import threading
import time
from typing import Callable, Optional


class ButtonInput:
    """A single push-button wired to a GPIO pin that fires a callback when pressed."""

    def __init__(self, pin: int, on_press: Callable[[], None], bounce_time: float = 0.05):
        self.pin = pin
        self._on_press = on_press
        self.bounce_time = bounce_time
        self._btn: Optional[object] = None

    def start(self) -> None:
        from gpiozero import Button  # lazy import — no crash on non-Pi
        self._btn = Button(self.pin, pull_up=True, bounce_time=self.bounce_time)
        self._btn.when_pressed = self._on_press

    def stop(self) -> None:
        if self._btn:
            self._btn.close()
            self._btn = None


class TuneInput:
    """Base class for physical (or virtual) tuning input devices."""

    def start(self, tune: Callable[[float], None]) -> None:
        """Register the tune callback and begin listening for input events."""

    def stop(self) -> None:
        """Stop listening and release hardware resources."""


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
        i2c_bus: int = 1,
        interrupt_pin: Optional[int] = None,
        poll_hz: float = 30.0,
    ):
        self.step = step
        self.i2c_addr = i2c_addr
        self.i2c_bus = i2c_bus
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
            self._ioe = io.IOE(i2c_addr=self.i2c_addr, smbus_id=self.i2c_bus, interrupt_pin=self.interrupt_pin)
            self._ioe.enable_interrupt_out(pin_swap=True)
        else:
            self._ioe = io.IOE(i2c_addr=self.i2c_addr, smbus_id=self.i2c_bus)

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


class TuningLED:
    """LED on a GPIO pin that indicates tuning proximity.

    Fades from off at the edge of the tuning window up to full brightness
    when fully locked to a station (gain == 1.0).
    """

    def __init__(self, pin: int, max_brightness: float = 1.0):
        self.pin = pin
        self._max_brightness = max(0.0, min(1.0, max_brightness))
        self._led: Optional[object] = None

    def start(self) -> None:
        from gpiozero import PWMLED  # lazy — no crash on non-Pi
        self._led = PWMLED(self.pin)

    def set_brightness(self, value: float) -> None:
        """Set LED brightness proportional to tuning gain (0.0–1.0)."""
        if self._led is None:
            return
        self._led.value = max(0.0, min(1.0, value)) * self._max_brightness

    def stop(self) -> None:
        if self._led:
            self._led.off()
            self._led.close()
            self._led = None


class VolumeInput:
    """Base class for physical (or virtual) volume input devices."""

    def start(self, set_volume: Callable[[int], None]) -> None:
        """Register the set_volume callback and begin listening for input events."""

    def stop(self) -> None:
        """Stop listening and release hardware resources."""


class PotentiometerInput(VolumeInput):
    """Pimoroni Potentiometer Breakout connected via I2C (addr 0x0E).

    Reads the potentiometer position and calls set_volume(0–100).
    Polled at poll_hz.  i2c_bus selects the SMBus device (0 = pins 27/28,
    1 = pins 3/5).
    """

    _ENC_A = 12
    _ENC_B = 3
    _ENC_C = 11

    def __init__(
        self,
        i2c_addr: int = 0x0E,
        poll_hz: float = 10.0,
        i2c_bus: int = 0,
    ):
        self.i2c_addr = i2c_addr
        self.i2c_bus = i2c_bus
        self._poll_interval = 1.0 / poll_hz
        self._set_volume: Optional[Callable[[int], None]] = None
        self._ioe: Optional[object] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self, set_volume: Callable[[int], None]) -> None:
        import ioexpander as io  # lazy — no crash on non-Pi

        self._set_volume = set_volume
        self._ioe = io.IOE(i2c_addr=self.i2c_addr, smbus_id=self.i2c_bus)

        self._ioe.set_mode(self._ENC_A, io.PIN_MODE_PP)
        self._ioe.set_mode(self._ENC_B, io.PIN_MODE_PP)
        self._ioe.set_mode(self._ENC_C, io.ADC)

        self._ioe.output(self._ENC_A, 1)
        self._ioe.output(self._ENC_B, 0)

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        ioe = self._ioe
        vref = ioe.get_adc_vref()
        while self._running:
            analog = ioe.input(self._ENC_C)
            volume = 100 - int((analog / vref) * 100)
            self._set_volume(volume)
            time.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._ioe = None
