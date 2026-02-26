# radio/station_config.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# tomllib is built-in on Python 3.11+
import tomllib


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, list):
        out: list[str] = []
        for x in v:
            if isinstance(x, str):
                xs = x.strip()
                if xs:
                    out.append(xs)
        return out
    return []


def _as_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _as_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


@dataclass(frozen=True)
class ScheduleEntry:
    """Represents a single schedule entry with tags and optional overlays."""
    tags: list[str]
    overlays_dir: str = ""
    overlays_probability: float = 0.0


def _normalize_schedule(raw: Any) -> dict[str, dict[int, ScheduleEntry]]:
    """
    Accepts schedule in TOML like:

      [schedule.monday]
      7 = { tags = "pop" }
      8 = { tags = ["pop", "rock"], overlays = "KHHZ-pop-overlays", overlays_probability = 0.3 }

    Produces: {"monday": {7: ScheduleEntry(...), 8: ScheduleEntry(...)}}
    """
    if not isinstance(raw, dict):
        return {}

    out: dict[str, dict[int, ScheduleEntry]] = {}
    for day, day_map in raw.items():
        if not isinstance(day, str) or not isinstance(day_map, dict):
            continue
        dkey = day.strip().lower()
        if not dkey:
            continue

        out[dkey] = {}
        for hour_key, rule in day_map.items():
            # TOML bare keys like 7 become int; quoted "7" become str.
            try:
                hr = int(hour_key)
            except Exception:
                continue
            if hr < 0 or hr > 23:
                continue

            tags: list[str] = []
            overlays_dir = ""
            overlays_probability = 0.0

            if isinstance(rule, dict):
                tags = _as_list(rule.get("tags"))
                # Accept both new name and old name for backwards compatibility
                overlays_dir = _as_str(
                    rule.get("overlays") or rule.get("interstitials")
                ).strip()
                prob = rule.get("overlays_probability") or rule.get("interstitials_probability")
                if prob is not None:
                    overlays_probability = max(0.0, min(1.0, _as_float(prob, 0.0)))

            out[dkey][hr] = ScheduleEntry(
                tags=tags,
                overlays_dir=overlays_dir,
                overlays_probability=overlays_probability
            )

    return out


@dataclass(frozen=True)
class StationConfig:
    """Full configuration for a single radio station, loaded from a TOML file."""

    name: str
    freq: float

    # Directories for station-only media
    idents_dir: str = ""
    commercials_dir: str = ""

    # Break config
    break_frequency_s: int = 0
    break_length_s: int = 0

    # Ident frequency (how often to play a between-song ident)
    ident_frequency_s: int = 0

    # Overlay config (overlays play over songs)
    overlay_pad_s: float = 0.0
    overlay_duck: float = 0.4
    overlay_ramp_s: float = 0.5

    # Top-of-the-hour jingle directory
    top_of_the_hour: str = ""

    # Schedule: day -> hour(int 0-23) -> ScheduleEntry
    schedule: dict[str, dict[int, ScheduleEntry]] = field(default_factory=dict)


def load_station_toml(path: str) -> StationConfig:
    """
    Loads a station config TOML.

    Expected TOML shape (example):

      name = "KHMR"
      freq = 89.9
      idents_dir = "/home/radio/radio-code/idents/KHMR"
      commercials_dir = "/home/radio/radio-code/commercials/KHMR"

      break_frequency_s = 900
      break_length_s = 60

      ident_frequency_s = 180

      overlay_pad_s = 2.0
      overlay_duck = 0.4
      overlay_ramp_s = 0.5

      [schedule.monday]
      7 = { tags = "pop", overlays = "KHMR-pop-overlays", overlays_probability = 0.3 }
      8 = { tags = "pop" }
      9 = { tags = ["pop", "rock"], overlays = "KHMR-mixed", overlays_probability = 1.0 }

      [schedule.tuesday]
      11 = { tags = "jazz" }

    Notes:
      - keys are tolerant: you can also use break_frequency, break_length, ident_frequency, etc.
      - schedule hour keys can be integers or strings.
      - overlays: directory path where overlay files are located (optional)
      - overlays_probability: 0.0-1.0, probability of playing overlay over a song (optional, default 0)
    """
    p = Path(path).expanduser()
    data = tomllib.loads(p.read_text(encoding="utf-8"))

    name = _as_str(data.get("name")).strip()
    if not name:
        # fallback: file stem
        name = p.stem

    freq = _as_float(data.get("freq"), 0.0)
    if freq <= 0:
        raise ValueError(f"{path}: missing/invalid freq")

    # Support either *_dir or *_dir*s* naming
    idents_dir = _as_str(data.get("idents_dir") or data.get("ident_dir")).strip()
    commercials_dir = _as_str(data.get("commercials_dir") or data.get("commercial_dir")).strip()

    # Support *_s or without suffix
    break_frequency_s = _as_int(data.get("break_frequency_s") or data.get("break_frequency") or 0, 0)
    break_length_s = _as_int(data.get("break_length_s") or data.get("break_length") or 0, 0)

    ident_frequency_s = _as_int(data.get("ident_frequency_s") or data.get("ident_frequency") or 0, 0)

    # Accept new names; fall back to old ident_ names for backwards compatibility
    overlay_pad_s = _as_float(
        data.get("overlay_pad_s") or data.get("overlay_pad")
        or data.get("ident_pad_s") or data.get("ident_pad") or 0.0, 0.0
    )
    overlay_duck = _as_float(
        data.get("overlay_duck") or data.get("ident_duck") or 0.4, 0.4
    )
    overlay_ramp_s = _as_float(
        data.get("overlay_ramp_s") or data.get("overlay_ramp")
        or data.get("ident_ramp_s") or data.get("ident_ramp") or 0.5, 0.5
    )

    top_of_the_hour = _as_str(data.get("top_of_the_hour")).strip()
    schedule = _normalize_schedule(data.get("schedule"))

    return StationConfig(
        name=name,
        freq=freq,
        idents_dir=idents_dir,
        commercials_dir=commercials_dir,
        break_frequency_s=break_frequency_s,
        break_length_s=break_length_s,
        ident_frequency_s=ident_frequency_s,
        overlay_pad_s=overlay_pad_s,
        overlay_duck=overlay_duck,
        overlay_ramp_s=overlay_ramp_s,
        top_of_the_hour=top_of_the_hour,
        schedule=schedule,
    )
