# radio/radio.py
from __future__ import annotations

import datetime
import glob
import math
import time
import threading
from dataclasses import dataclass
from typing import Optional

import uvicorn

from .config import RadioConfig
from .db import connect
from .input import TuneInput, VolumeInput, TuningLED, ButtonInput
from .station_config import load_station_toml, StationConfig
from .scheduler import Scheduler, NowPlaying
from .player import Player, PlayerConfig
from .api import create_api
from . import terminal as T


# -------------------- Helpers --------------------

def clamp_freq(v: float, freq_min: float, freq_max: float, step: float = 0.1) -> float:
    decimals = max(1, -int(math.floor(math.log10(step)))) if step > 0 else 1
    return round(max(freq_min, min(freq_max, v)), decimals)


def gain_from_delta(delta: float, lock_window: float, fade_window: float) -> float:
    if delta <= lock_window:
        return 1.0
    if delta <= lock_window + fade_window:
        return 1.0 - (delta - lock_window) / fade_window
    return 0.0


def sorted_stations(cfgs: dict[str, StationConfig]):
    sts = sorted(((name, float(cfg.freq)) for name, cfg in cfgs.items()), key=lambda x: x[1])
    if not sts:
        raise RuntimeError("No stations loaded")
    return sts


def midpoints(sts):
    if len(sts) < 2:
        return []
    return [(sts[i][1] + sts[i + 1][1]) / 2.0 for i in range(len(sts) - 1)]


def nearest_station(freq: float, sts, mids):
    if not mids:
        return sts[0]
    for i, m in enumerate(mids):
        if freq < m:
            return sts[i]
    return sts[-1]


def _basename(p: Optional[str]) -> str:
    if not p:
        return "—"
    return p.split("/")[-1]


# -------------------- Radio Runtime --------------------

@dataclass
class TuningState:
    """Current state of the FM dial, including the nearest station and signal mix level."""

    freq: float = 90.0
    station_name: Optional[str] = None
    station_freq: Optional[float] = None
    base_music_vol: int = 0  # 0-100


class RadioApp:
    """Main radio application coordinating the scheduler, player, and GPIO input."""

    def __init__(
        self,
        config: RadioConfig,
        inputs: list[TuneInput] | None = None,
        volume_inputs: list[VolumeInput] | None = None,
        tuning_led: TuningLED | None = None,
        verbosity: str = "normal",
    ):
        self.config = config
        self._verbosity = verbosity  # "quiet" | "normal" | "verbose"

        # Load station configs
        paths = sorted(glob.glob(self.config.station_tomls_glob))
        if not paths:
            raise RuntimeError(f"No station TOMLs found at {self.config.station_tomls_glob}")

        self.station_cfgs: dict[str, StationConfig] = {}
        for p in paths:
            cfg = load_station_toml(p)
            self.station_cfgs[cfg.name] = cfg

        self.sts = sorted_stations(self.station_cfgs)
        self.mids = midpoints(self.sts)

        # DB + scheduler
        self.con = connect(self.config.db_path)
        self.scheduler = Scheduler(
            self.con, self.station_cfgs,
            overlay_pad_s=self.config.overlay_pad_s,
            overlay_duck=self.config.overlay_duck,
            overlay_ramp_s=self.config.overlay_ramp_s,
        )

        # Player
        pcfg = PlayerConfig(
            audio_device=self.config.audio_device,
            master_vol=self.config.master_vol,
            radio_af=self.config.radio_af,
        )
        self.player = Player(self.config.noise_file, pcfg)

        # tuning state
        self.state = TuningState(freq=90.0)

        # lock and mute state must be set before any input callbacks are registered
        self._lock = threading.Lock()
        self._muted = False
        self._last_vol: int = self.config.master_vol

        # input devices
        self._inputs = inputs or []
        for inp in self._inputs:
            inp.start(self.tune)

        self._volume_inputs = volume_inputs or []
        for inp in self._volume_inputs:
            inp.start(self.set_volume)

        self._tuning_led = tuning_led
        if self._tuning_led:
            self._tuning_led.start()

        # buttons from config — values are RadioApp method names
        self._button_inputs: list[ButtonInput] = []
        for pin, action in self.config.buttons:
            fn = getattr(self, action, None)
            if fn is None or not callable(fn):
                print(f"Warning: no callable method '{action}' on RadioApp for GPIO {pin}, skipping")
                continue
            btn = ButtonInput(pin, on_press=fn)
            btn.start()
            self._button_inputs.append(btn)

        # minimal logging state: only print on program change / ident overlay trigger
        self._last_program_sig: Optional[tuple] = None
        self._last_ident_sig: Optional[tuple] = None

    def _log(self, *args, **kwargs) -> None:
        """Print unless in quiet mode."""
        if self._verbosity != "quiet":
            print(*args, **kwargs)

    def _maybe_log_and_play(self, np: NowPlaying) -> None:
        """
        Forward NowPlaying to the player, logging only when something changes.

        Prints when:
          - the main program changes (station, kind, or path)
          - an ident overlay is newly triggered
        """
        program_sig = (np.station, np.kind, np.path)
        if program_sig != self._last_program_sig:
            self._last_program_sig = program_sig
            if self._verbosity != "quiet":
                is_ident = np.kind == "ident"
                if self._verbosity == "verbose":
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    if is_ident:
                        tag = f"{T.BOLD}{T.BRIGHT_YELLOW}[IDENT {ts}]{T.RESET}"
                    else:
                        tag = f"{T.BOLD}{T.BRIGHT_GREEN}[PLAY {ts}]{T.RESET}"
                    filepath = np.path or "—"
                else:
                    if is_ident:
                        tag = f"{T.BOLD}{T.BRIGHT_YELLOW}[IDENT]{T.RESET}"
                    else:
                        tag = f"{T.BOLD}{T.BRIGHT_GREEN}[PLAY]{T.RESET}"
                    filepath = _basename(np.path)
                print(
                    f"{tag} {T.BOLD}{T.BRIGHT_CYAN}{np.station}{T.RESET}"
                    f"  {T.YELLOW}{np.kind}{T.RESET}: {T.BRIGHT_WHITE}{filepath}{T.RESET}"
                )

        ident_sig = None
        if np.ident_overlay:
            ident_sig = (np.station, np.ident_overlay.path, float(np.ident_overlay.at_s))
        if ident_sig and ident_sig != self._last_ident_sig:
            self._last_ident_sig = ident_sig
            if self._verbosity != "quiet":
                if self._verbosity == "verbose":
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    tag = f"{T.BOLD}{T.BRIGHT_MAGENTA}[OVERLAY {ts}]{T.RESET}"
                    filepath = np.ident_overlay.path
                else:
                    tag = f"{T.BOLD}{T.BRIGHT_MAGENTA}[OVERLAY]{T.RESET}"
                    filepath = _basename(np.ident_overlay.path)
                print(
                    f"{tag} {T.BOLD}{T.BRIGHT_CYAN}{np.station}{T.RESET}"
                    f": {T.BRIGHT_WHITE}{filepath}{T.RESET}"
                )

        # Always call play(); Player should be idempotent and handle seeks/overlays correctly.
        self.player.play(np)

    def set_volume(self, level: int) -> None:
        """Set the master volume (0–100) from a physical volume input."""
        self._last_vol = level
        if not self._muted:
            self.player.set_master_vol(level)

    def tune_next_station(self) -> None:
        """Cycle to the next station by frequency, wrapping back to the first."""
        with self._lock:
            names = [name for name, _ in self.sts]
            current = self.state.station_name
            idx = (names.index(current) + 1) % len(names) if current in names else 0
            next_name, next_freq = self.sts[idx]

            self.state.freq = next_freq
            self.state.station_name = next_name
            self.state.station_freq = next_freq
            self.state.base_music_vol = 100
            self.player.set_mix(100)
            if self._tuning_led:
                self._tuning_led.set_brightness(1.0)

            np = self.scheduler.ensure_station_current(next_name, time.time(), active=True)
            self._log(
                f"{T.CYAN}Station \u2192 {T.BOLD}{T.BRIGHT_CYAN}{next_name}{T.RESET}"
                f"{T.CYAN} @ {T.MAGENTA}{next_freq:.1f}{T.CYAN} FM{T.RESET}"
            )
            self._maybe_log_and_play(np)

    def toggle_mute(self) -> None:
        """Toggle mute. Restores to the current potentiometer position or last known volume."""
        if self._muted:
            self._muted = False
            self.player.set_master_vol(self._last_vol)
        else:
            self._last_vol = self.player.cfg.master_vol
            self._muted = True
            self.player.set_master_vol(0)

    def tune(self, delta: float) -> None:
        """Adjust the dial by delta MHz, updating station selection and audio mix accordingly."""
        with self._lock:
            self.state.freq = clamp_freq(
                self.state.freq + delta, self.config.freq_min, self.config.freq_max, self.config.step
            )
            name, sf = nearest_station(self.state.freq, self.sts, self.mids)

            d = abs(self.state.freq - sf)
            g = gain_from_delta(d, self.config.lock_window, self.config.fade_window)
            self.state.base_music_vol = int(g * 100)

            # crossfade mix immediately for responsiveness
            self.player.set_mix(self.state.base_music_vol)

            if self._tuning_led:
                self._tuning_led.set_brightness(g)

            if self._verbosity == "verbose":
                self._log(
                    f"{T.DIM}Dial: {T.MAGENTA}{self.state.freq:.1f} FM{T.RESET}"
                    f"{T.DIM}  (nearest {T.CYAN}{name}{T.DIM}"
                    f" @ {T.MAGENTA}{sf:.1f}{T.DIM},"
                    f" mix={T.YELLOW}{self.state.base_music_vol}%{T.DIM}){T.RESET}"
                )

            # If station changed, force an immediate program refresh
            if self.state.station_name != name:
                self.state.station_name = name
                self.state.station_freq = sf

                # Only mark station as active if it's actually audible
                active = self.state.base_music_vol > 0
                np = self.scheduler.ensure_station_current(name, time.time(), active=active)

                self._log(
                    f"{T.CYAN}Station \u2192 {T.BOLD}{T.BRIGHT_CYAN}{name}{T.RESET}"
                    f"{T.CYAN} @ {T.MAGENTA}{sf:.1f}{T.CYAN} FM{T.RESET}"
                )
                self._maybe_log_and_play(np)

    def run(self) -> None:
        """Start the main event loop, ticking all stations until interrupted."""
        # Start API server in background daemon thread
        fastapi_app = create_api(self)
        api_thread = threading.Thread(
            target=uvicorn.run,
            kwargs={
                "app": fastapi_app,
                "host": self.config.api_host,
                "port": self.config.api_port,
                "log_level": "warning",
            },
            daemon=True,
        )
        api_thread.start()

        # initial tune
        self.tune(0.0)
        self._log(
            f"{T.BOLD}{T.BRIGHT_GREEN}Radio running.{T.RESET}"
            f"  {T.DIM}Ctrl+C to exit.{T.RESET}"
        )

        try:
            while True:
                now = time.time()

                # Keep all stations progressing while you're not tuned to them
                self.scheduler.tick_all(now)

                # If tuned close enough to a station, ensure the current program is correct
                with self._lock:
                    st = self.state.station_name
                    base = self.state.base_music_vol

                if st and base > 0:
                    # active=True ONLY for the audible/closest station
                    np = self.scheduler.ensure_station_current(st, now, active=True)
                    self._maybe_log_and_play(np)

                time.sleep(self.config.tick_s)

        except KeyboardInterrupt:
            pass
        finally:
            for inp in self._inputs:
                try:
                    inp.stop()
                except Exception:
                    pass
            for inp in self._volume_inputs:
                try:
                    inp.stop()
                except Exception:
                    pass
            for btn in self._button_inputs:
                try:
                    btn.stop()
                except Exception:
                    pass
            try:
                self.player.stop()
            except Exception:
                pass
            if self._tuning_led:
                try:
                    self._tuning_led.stop()
                except Exception:
                    pass
            try:
                self.con.close()
            except Exception:
                pass
