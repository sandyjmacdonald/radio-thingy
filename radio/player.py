# radio/player.py
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

import mpv

from .scheduler import NowPlaying, OverlayIdent


def clampi(v: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(v)))


def scale(vol_0_100: int, master_0_100: int) -> int:
    vol = clampi(vol_0_100)
    master = clampi(master_0_100)
    return int(vol * (master / 100.0))


@dataclass
class PlayerConfig:
    """Configuration for the Player's three MPV instances."""

    audio_device: str = "pipewire"
    master_vol: int = 60  # 0-100 applied to everything
    radio_af: Optional[str] = None  # mpv af string (lavfi=...) or None


class Player:
    """
    Owns three MPV instances for simultaneous audio output.

    Instances:
      - noise: loops constantly
      - music: single instance for program audio (song/ident/commercial)
      - ident: overlay instance (plays idents over music)

    The caller controls:
      - set_mix(base_music_vol_0_100): 0 means all noise, 100 means all music.
      - play(nowplaying): load/seek correct media for tuned station
    """

    def __init__(self, noise_path: str, cfg: PlayerConfig):
        self.cfg = cfg
        self.noise_path = noise_path

        # state
        self.current_station: Optional[str] = None
        self.current_kind: Optional[str] = None
        self.current_path: Optional[str] = None
        self.current_media_id: Optional[int] = None
        self.current_started_ts: float = 0.0
        self._base_music_vol: int = 0

        # ident overlay scheduling + ducking
        self._ident_timer: Optional[threading.Timer] = None
        self._ducking = False
        self._duck_factor = 1.0
        self._duck_ramp_s = 0.5
        self._duck_target_factor = 1.0

        # ramp token to cancel old ramps
        self._ramp_lock = threading.Lock()
        self._ramp_token = 0

        # mpv common opts
        common_opts = dict(
            audio_device=self.cfg.audio_device,
            vid="no",
            force_window="no",
            audio_display="no",
            terminal="no",
            msg_level="all=warn",
        )

        # Noise player (always looping)
        self.noise = mpv.MPV(**common_opts)
        self.noise.loop_file = "inf"
        self.noise.volume = scale(100, self.cfg.master_vol)
        self.noise.play(self.noise_path)

        # Music player
        music_opts = dict(common_opts)
        if self.cfg.radio_af:
            music_opts["af"] = self.cfg.radio_af
        self.music = mpv.MPV(**music_opts)
        self.music.volume = 0

        # Ident overlay player
        ident_opts = dict(common_opts)
        if self.cfg.radio_af:
            ident_opts["af"] = self.cfg.radio_af
        self.ident = mpv.MPV(**ident_opts)
        self.ident.volume = scale(100, self.cfg.master_vol)

        @self.ident.event_callback("end-file")
        def _on_ident_end(_evt):
            # un-duck smoothly
            self._start_duck_ramp(target_factor=1.0)

    # -------------------- Mix Control --------------------

    def set_mix(self, base_music_vol_0_100: int) -> None:
        """Crossfade between noise and music based on tuning position."""
        self._base_music_vol = clampi(base_music_vol_0_100)
        self._apply_volumes()

    def _apply_volumes(self) -> None:
        master = clampi(self.cfg.master_vol)
        base = clampi(self._base_music_vol)

        # Noise opposite
        noise_vol = clampi(100 - base)
        self.noise.volume = scale(noise_vol, master)

        # Music is base * duck_factor
        eff = int(base * self._duck_factor)
        self.music.volume = scale(clampi(eff), master)

        # ident always obey master (volume fixed at 100% * master)
        self.ident.volume = scale(100, master)

    # -------------------- Program Control --------------------

    def stop(self) -> None:
        """Stop all program audio and cancel any pending ident overlay."""
        self._cancel_ident_timer()
        try:
            self.music.command("stop")
        except Exception:
            pass
        try:
            self.ident.command("stop")
        except Exception:
            pass

    def play(self, np: NowPlaying) -> None:
        """
        Ensure the tuned station is playing what the scheduler says it should be.

        Seeks to np.seek_s for continuity when re-tuning mid-track.
        """
        if np.kind == "noise":
            # No program audio, just noise (mix should already be at 0 if you're not locked)
            self.current_station = np.station
            self.current_kind = "noise"
            self.current_path = None
            self.current_media_id = None
            self.current_started_ts = np.started_ts
            self._cancel_ident_timer()
            return

        if not np.path:
            return

        needs_load = (
            self.current_station != np.station
            or self.current_kind != np.kind
            or self.current_path != np.path
            or self.current_media_id != np.media_id
            or abs(self.current_started_ts - np.started_ts) > 0.25
        )

        if needs_load:
            # cancel any ident schedule from previous program
            self._cancel_ident_timer()

            # Reset ducking when switching program content
            self._start_duck_ramp(target_factor=1.0)

            self.current_station = np.station
            self.current_kind = np.kind
            self.current_path = np.path
            self.current_media_id = np.media_id
            self.current_started_ts = np.started_ts

            # Replace the current file in the SAME mpv instance (no new threads)
            self.music.command("loadfile", np.path, "replace")

            # Seek for continuity (songs should resume where they ought to be)
            if np.seek_s > 0.1:
                self._seek_when_ready(np.seek_s)

        # schedule overlay ident if provided (only meaningful for kind == song)
        if np.ident_overlay and np.kind == "song":
            self._schedule_overlay_ident(np, np.ident_overlay)

        # volumes may have changed
        self._apply_volumes()

    def _seek_when_ready(self, target_s: float, timeout_s: float = 2.0) -> None:
        """Seek to target_s, retrying briefly since MPV may reject seeks immediately after loadfile."""
        target_s = max(0.0, float(target_s))
        t0 = time.monotonic()
        while (time.monotonic() - t0) < timeout_s:
            try:
                dur = self.music.duration
                if dur and dur > 5:
                    # Clamp slightly from the end
                    off = min(target_s, max(0.0, float(dur) - 1.0))
                    self.music.command("seek", off, "absolute", "exact")
                    return
            except Exception:
                pass
            time.sleep(0.05)

    # -------------------- Ident Overlay and Ducking --------------------

    def _cancel_ident_timer(self) -> None:
        if self._ident_timer is not None:
            try:
                self._ident_timer.cancel()
            except Exception:
                pass
            self._ident_timer = None

    def _schedule_overlay_ident(self, np: NowPlaying, ov: OverlayIdent) -> None:
        """Schedule the ident to fire at ov.at_s seconds into the song."""
        self._cancel_ident_timer()

        # If we're already past that point, start ASAP (but still duck smoothly)
        when_ts = np.started_ts + float(ov.at_s)
        delay = max(0.0, when_ts - time.time())

        def fire(token_station: str, token_started_ts: float, ident_path: str):
            # Only fire if still on same station + same program instance
            if self.current_station != token_station:
                return
            if abs(self.current_started_ts - token_started_ts) > 0.25:
                return

            # Duck down, then play ident overlay
            self._start_duck_ramp(target_factor=max(0.0, min(1.0, float(ov.duck))))
            try:
                self.ident.command("loadfile", ident_path, "replace")
            except Exception:
                # if ident fails, un-duck
                self._start_duck_ramp(target_factor=1.0)

        self._ident_timer = threading.Timer(
            delay,
            fire,
            args=(np.station, np.started_ts, ov.path),
        )
        self._ident_timer.daemon = True
        self._ident_timer.start()

        # ramp duration can be station-specific; store it for duck ramps
        self._duck_ramp_s = max(0.0, float(ov.ramp_s))

    def _start_duck_ramp(self, target_factor: float) -> None:
        """Smoothly ramp duck_factor to target_factor over self._duck_ramp_s seconds."""
        target = max(0.0, min(1.0, float(target_factor)))
        ramp_s = max(0.0, float(self._duck_ramp_s))

        with self._ramp_lock:
            self._ramp_token += 1
            token = self._ramp_token

        start = float(self._duck_factor)
        if ramp_s <= 0.01 or abs(target - start) < 0.001:
            self._duck_factor = target
            self._apply_volumes()
            return

        steps = max(5, int(ramp_s / 0.05))
        dt = ramp_s / steps

        def run():
            for i in range(1, steps + 1):
                with self._ramp_lock:
                    if token != self._ramp_token:
                        return
                self._duck_factor = start + (target - start) * (i / steps)
                self._apply_volumes()
                time.sleep(dt)

            self._duck_factor = target
            self._apply_volumes()

        threading.Thread(target=run, daemon=True).start()
