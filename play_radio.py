#!/usr/bin/env python3
"""Entry point for the physical radio — loads config and wires up input devices."""
import argparse

from radio.config import load_config
from radio.input import RgbEncoderInput, PotentiometerInput, TuningLED
from radio.radio import RadioApp

DEFAULT_CONFIG = "/home/radio/deadair/config.toml"


def main() -> None:
    ap = argparse.ArgumentParser(description="Dead Air — FM radio simulator")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help=f"Path to config.toml (default: {DEFAULT_CONFIG})")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--verbose", action="store_true", help="Verbose output: timestamps, full paths, dial position")
    group.add_argument("--quiet", action="store_true", help="Suppress all non-error output")
    args = ap.parse_args()

    verbosity = "verbose" if args.verbose else "quiet" if args.quiet else "normal"

    cfg = load_config(args.config)
    volume_inputs = [PotentiometerInput(i2c_bus=cfg.potentiometer_i2c_bus)] if cfg.potentiometer else []
    tuning_led = TuningLED(cfg.tuning_led_pin, max_brightness=cfg.led_brightness) if cfg.tuning_led_pin is not None else None
    app = RadioApp(
        config=cfg,
        inputs=[RgbEncoderInput(cfg.step, i2c_bus=cfg.encoder_i2c_bus, interrupt_pin=cfg.encoder_interrupt_pin)],
        volume_inputs=volume_inputs,
        tuning_led=tuning_led,
        verbosity=verbosity,
    )
    app.run()


if __name__ == "__main__":
    main()
