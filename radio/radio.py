# radio/radio.py
from __future__ import annotations

import glob
import time
import threading
from dataclasses import dataclass
from typing import Optional

from gpiozero import Button

from .db import connect
from .station_config import load_station_toml, StationConfig
from .scheduler import Scheduler, NowPlaying
from .player import Player, PlayerConfig


# -------------------- CONFIG --------------------

BASE_DIR = "/home/radio/radio-code"
DB_PATH = f"{BASE_DIR}/radio.db"

STATION_TOMLS_GLOB = f"{BASE_DIR}/stations/*.toml"

NOISE_FILE = f"/home/radio/media/effects/noise.mp3"

AUDIO_DEVICE = "pipewire"     # run WITHOUT sudo
MASTER_VOL = 60               # global master 0-100

# Dial/tuning behaviour
FREQ_MIN = 88.0
FREQ_MAX = 98.0
STEP = 0.1

LOCK_WINDOW = 0.2
FADE_WINDOW = 0.5

# Buttons (active low)
BTN_DOWN = 5
BTN_UP = 6

# Optional radio “processing” (can be None if you want raw)
RADIO_AF = (
    "lavfi=["
    "highpass=f=70,"
    "lowpass=f=15000,"
    "acompressor=threshold=-20dB:ratio=4:attack=4:release=140:makeup=7:knee=6dB,"
    "alimiter=limit=0.97"
    "]"
)

# Main loop tick
TICK_S = 0.25

# -------------------- Helpers --------------------

def clamp_freq(v: float) -> float:
    return round(max(FREQ_MIN, min(FREQ_MAX, v)), 1)


def gain_from_delta(delta: float) -> float:
    if delta <= LOCK_WINDOW:
        return 1.0
    if delta <= LOCK_WINDOW + FADE_WINDOW:
        return 1.0 - (delta - LOCK_WINDOW) / FADE_WINDOW
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


# -------------------- Radio runtime --------------------

@dataclass
class TuningState:
    freq: float = 90.0
    station_name: Optional[str] = None
    station_freq: Optional[float] = None
    base_music_vol: int = 0  # 0-100


class RadioApp:
    def __init__(self):
        # Load station configs
        paths = sorted(glob.glob(STATION_TOMLS_GLOB))
        if not paths:
            raise RuntimeError(f"No station TOMLs found at {STATION_TOMLS_GLOB}")

        self.station_cfgs: dict[str, StationConfig] = {}
        for p in paths:
            cfg = load_station_toml(p)
            self.station_cfgs[cfg.name] = cfg

        self.sts = sorted_stations(self.station_cfgs)
        self.mids = midpoints(self.sts)

        # DB + scheduler
        self.con = connect(DB_PATH)
        self.scheduler = Scheduler(self.con, self.station_cfgs)

        # Player
        pcfg = PlayerConfig(
            audio_device=AUDIO_DEVICE,
            master_vol=MASTER_VOL,
            radio_af=RADIO_AF,
        )
        self.player = Player(NOISE_FILE, pcfg)

        # tuning state
        self.state = TuningState(freq=90.0)

        # input buttons
        self.btn_down = Button(BTN_DOWN, pull_up=True, bounce_time=0.05)
        self.btn_up = Button(BTN_UP, pull_up=True, bounce_time=0.05)
        self.btn_down.when_pressed = lambda: self.tune(-STEP)
        self.btn_up.when_pressed = lambda: self.tune(+STEP)

        # lock for tune() calls (gpio callbacks are threaded)
        self._lock = threading.Lock()

        # minimal logging state: only print on program change / ident overlay trigger
        self._last_program_sig: Optional[tuple] = None
        self._last_ident_sig: Optional[tuple] = None

    def _maybe_log_and_play(self, np: NowPlaying) -> None:
        """
        Only print when:
          - the main program changes (song/commercial/ident/noise path)
          - an ident overlay is triggered (the scheduler requested one)
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
        with self._lock:
            self.state.freq = clamp_freq(self.state.freq + delta)
            name, sf = nearest_station(self.state.freq, self.sts, self.mids)

            d = abs(self.state.freq - sf)
            g = gain_from_delta(d)
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
        # initial tune
        self.tune(0.0)
        print("Radio running. Ctrl+C to exit.")

        try:
            while True:
                now = time.time()

                # Keep all stations progressing while you’re not tuned to them
                self.scheduler.tick_all(now)

                # If tuned close enough to a station, ensure the current program is correct
                with self._lock:
                    st = self.state.station_name
                    base = self.state.base_music_vol

                if st and base > 0:
                    # active=True ONLY for the audible/closest station
                    np = self.scheduler.ensure_station_current(st, now, active=True)
                    self._maybe_log_and_play(np)

                time.sleep(TICK_S)

        except KeyboardInterrupt:
            pass
        finally:
            try:
                self.player.stop()
            except Exception:
                pass
            try:
                self.con.close()
            except Exception:
                pass


def main() -> None:
    app = RadioApp()
    app.run()


if __name__ == "__main__":
    main()
