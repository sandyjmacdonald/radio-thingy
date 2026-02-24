# radio/radio.py
from __future__ import annotations

import glob
import time
import threading
from dataclasses import dataclass
from typing import Optional

import uvicorn

from .config import RadioConfig
from .db import connect
from .input import TuneInput
from .station_config import load_station_toml, StationConfig
from .scheduler import Scheduler, NowPlaying
from .player import Player, PlayerConfig
from .api import create_api


# -------------------- Helpers --------------------

def clamp_freq(v: float, freq_min: float, freq_max: float) -> float:
    return round(max(freq_min, min(freq_max, v)), 1)


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

    def __init__(self, config: RadioConfig, inputs: list[TuneInput] | None = None):
        self.config = config

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
        self.scheduler = Scheduler(self.con, self.station_cfgs)

        # Player
        pcfg = PlayerConfig(
            audio_device=self.config.audio_device,
            master_vol=self.config.master_vol,
            radio_af=self.config.radio_af,
        )
        self.player = Player(self.config.noise_file, pcfg)

        # tuning state
        self.state = TuningState(freq=90.0)

        # input devices
        self._inputs = inputs or []
        for inp in self._inputs:
            inp.start(self.tune)

        # lock for tune() calls (gpio callbacks are threaded)
        self._lock = threading.Lock()

        # minimal logging state: only print on program change / ident overlay trigger
        self._last_program_sig: Optional[tuple] = None
        self._last_ident_sig: Optional[tuple] = None

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
            print(f"[PLAY] {np.station} {np.kind}: {_basename(np.path)}")

        ident_sig = None
        if np.ident_overlay:
            ident_sig = (np.station, np.ident_overlay.path, float(np.ident_overlay.at_s))
        if ident_sig and ident_sig != self._last_ident_sig:
            self._last_ident_sig = ident_sig
            print(f"[IDENT] {np.station}: {_basename(np.ident_overlay.path)}")

        # Always call play(); Player should be idempotent and handle seeks/overlays correctly.
        self.player.play(np)

    def tune(self, delta: float) -> None:
        """Adjust the dial by delta MHz, updating station selection and audio mix accordingly."""
        with self._lock:
            self.state.freq = clamp_freq(
                self.state.freq + delta, self.config.freq_min, self.config.freq_max
            )
            name, sf = nearest_station(self.state.freq, self.sts, self.mids)

            d = abs(self.state.freq - sf)
            g = gain_from_delta(d, self.config.lock_window, self.config.fade_window)
            self.state.base_music_vol = int(g * 100)

            # crossfade mix immediately for responsiveness
            self.player.set_mix(self.state.base_music_vol)

            # print dial info (kept as-is)
            print(f"Dial: {self.state.freq:.1f} FM  (nearest {name} @ {sf:.1f}, mix={self.state.base_music_vol}%)")

            # If station changed, force an immediate program refresh
            if self.state.station_name != name:
                self.state.station_name = name
                self.state.station_freq = sf

                # Only mark station as active if it's actually audible
                active = self.state.base_music_vol > 0
                np = self.scheduler.ensure_station_current(name, time.time(), active=active)

                print(f"Station changed to {name} @ {sf:.1f} FM")
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
        print("Radio running. Ctrl+C to exit.")

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
            try:
                self.player.stop()
            except Exception:
                pass
            try:
                self.con.close()
            except Exception:
                pass
