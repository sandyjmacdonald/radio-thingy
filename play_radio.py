#!/usr/bin/env python3
"""Entry point for the physical radio — loads config and wires up GPIO buttons."""
from radio.config import load_config
from radio.input import GpioButtonInput
from radio.radio import RadioApp

CONFIG_PATH = "/home/radio/radio-code/config.toml"

BTN_DOWN = 5
BTN_UP = 6

cfg = load_config(CONFIG_PATH)
app = RadioApp(config=cfg, inputs=[GpioButtonInput(BTN_DOWN, BTN_UP, cfg.step)])
app.run()
