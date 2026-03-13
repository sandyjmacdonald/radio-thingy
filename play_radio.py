#!/usr/bin/env python3
"""Entry point for the physical radio — loads config and wires up input devices."""
import argparse

from radio.config import load_config
from radio.input import RgbEncoderInput, PotentiometerInput
from radio.radio import RadioApp

DEFAULT_CONFIG = "/home/radio/deadair/config.toml"


def main() -> None:
    ap = argparse.ArgumentParser(description="Dead Air — FM radio simulator")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help=f"Path to config.toml (default: {DEFAULT_CONFIG})")
    ap.add_argument(
        "--interrupt-pin",
        type=int,
        default=4,
        metavar="GPIO",
        help="Pi GPIO pin wired to the encoder's INT header (default: 4)",
    )
    ap.add_argument(
        "--potentiometer",
        action="store_true",
        help="Enable the Pimoroni Potentiometer Breakout (I2C addr 0x0E) for volume control",
    )
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--verbose", action="store_true", help="Verbose output: timestamps, full paths, dial position")
    group.add_argument("--quiet", action="store_true", help="Suppress all non-error output")
    args = ap.parse_args()

    verbosity = "verbose" if args.verbose else "quiet" if args.quiet else "normal"

    cfg = load_config(args.config)
    volume_inputs = [PotentiometerInput()] if args.potentiometer else []
    app = RadioApp(
        config=cfg,
        inputs=[RgbEncoderInput(cfg.step, interrupt_pin=args.interrupt_pin)],
        volume_inputs=volume_inputs,
        verbosity=verbosity,
    )
    app.run()


if __name__ == "__main__":
    main()
