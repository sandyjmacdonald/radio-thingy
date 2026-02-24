from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RadioConfig:
    # Required paths
    db_path: str
    station_tomls_glob: str
    noise_file: str
    # Audio
    audio_device: str = "pipewire"
    master_vol: int = 60
    radio_af: Optional[str] = None
    # Dial
    freq_min: float = 88.0
    freq_max: float = 98.0
    step: float = 0.1
    lock_window: float = 0.2
    fade_window: float = 0.5
    # Runtime
    tick_s: float = 0.25
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000


def load_config(path: str) -> RadioConfig:
    p = Path(path).expanduser()
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return RadioConfig(
        db_path=data["db_path"],
        station_tomls_glob=data["station_tomls_glob"],
        noise_file=data["noise_file"],
        audio_device=data.get("audio_device", "pipewire"),
        master_vol=int(data.get("master_vol", 60)),
        radio_af=data.get("radio_af"),
        freq_min=float(data.get("freq_min", 88.0)),
        freq_max=float(data.get("freq_max", 98.0)),
        step=float(data.get("step", 0.1)),
        lock_window=float(data.get("lock_window", 0.2)),
        fade_window=float(data.get("fade_window", 0.5)),
        tick_s=float(data.get("tick_s", 0.25)),
        api_host=data.get("api_host", "0.0.0.0"),
        api_port=int(data.get("api_port", 8000)),
    )
