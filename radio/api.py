# radio/api.py
from __future__ import annotations

import datetime
import time
from typing import TYPE_CHECKING, Any, Optional

from fastapi import FastAPI, HTTPException

from . import helpers
from .db import connect

if TYPE_CHECKING:
    from .radio import RadioApp


def _build_now_playing(
    con: Any, row: Any
) -> Optional[dict[str, Any]]:
    """Build now_playing dict from a station_state row."""
    if row is None or row["kind"] == "noise":
        return {"type": "noise"}

    now = time.time()

    media_row: Optional[Any] = None
    if row["current_media_id"] is not None:
        media_row = helpers.get_one(
            con,
            "SELECT artist, title FROM media WHERE id=?",
            (int(row["current_media_id"]),),
        )

    started_at = (
        datetime.datetime.fromtimestamp(float(row["started_ts"]), tz=datetime.timezone.utc).isoformat(timespec="milliseconds")
        if row["started_ts"] is not None else None
    )
    ends_at = (
        datetime.datetime.fromtimestamp(float(row["ends_ts"]), tz=datetime.timezone.utc).isoformat(timespec="milliseconds")
        if row["ends_ts"] is not None else None
    )
    duration_s = round(float(row["duration_s"]), 2) if row["duration_s"] is not None else None
    started_ts_raw = float(row["started_ts"]) if row["started_ts"] is not None else None

    return {
        "type": row["kind"],
        "artist": media_row["artist"] if media_row else None,
        "title": media_row["title"] if media_row else None,
        "started_at": started_at,
        "ends_at": ends_at,
        "duration_s": duration_s,
        "elapsed_s": round(now - started_ts_raw, 2) if started_ts_raw is not None else None,
    }


def create_api(app: RadioApp) -> FastAPI:
    fastapi_app = FastAPI()
    con = connect(app.config.db_path)

    def _get_status(station: Optional[str] = None) -> dict[str, Any]:
        # Read tuning state under lock
        with app._lock:
            dial_freq = app.state.freq
            current_station = app.state.station_name
            base_music_vol = app.state.base_music_vol

        if station is not None:
            # --- Station-specific query ---
            if station not in app.station_cfgs:
                raise HTTPException(status_code=404, detail=f"Station not found: {station}")

            station_cfg = app.station_cfgs[station]
            target_freq = float(station_cfg.freq)
            tuned = current_station == station and base_music_vol > 0

            base: dict[str, Any] = {
                "frequency": target_freq,
                "station": station,
                "station_type": station_cfg.station_type,
                "tuned": tuned,
            }

            if station_cfg.station_type == "stream":
                return {**base, "now_playing": None}

            try:
                sid = helpers.station_id(con, station)
            except RuntimeError:
                return {**base, "now_playing": None}

            row = helpers.get_station_state(con, sid)
            return {**base, "now_playing": _build_now_playing(con, row)}

        # --- Current tuning state ---
        tuned = base_music_vol > 0 and current_station is not None
        current_station_type = app.station_cfgs[current_station].station_type if current_station else "regular"

        base = {
            "frequency": dial_freq,
            "station": current_station,
            "station_type": current_station_type,
            "tuned": tuned,
        }

        if not tuned:
            return {**base, "now_playing": None}

        if current_station_type == "stream":
            return {**base, "now_playing": None}

        try:
            sid = helpers.station_id(con, current_station)
        except RuntimeError:
            return {**base, "now_playing": None}

        row = helpers.get_station_state(con, sid)
        return {**base, "now_playing": _build_now_playing(con, row)}

    @fastapi_app.get("/stations")
    def stations_list() -> list[dict[str, Any]]:
        """Return all stations sorted by frequency."""
        return [
            {"name": name, "frequency": freq, "station_type": app.station_cfgs[name].station_type}
            for name, freq in app.sts
        ]

    @fastapi_app.get("/status")
    def status(station: Optional[str] = None) -> dict[str, Any]:
        return _get_status(station)

    @fastapi_app.post("/tune")
    def tune(
        station: Optional[str] = None,
        frequency: Optional[float] = None,
    ) -> dict[str, Any]:
        """Tune the dial to a station by name or to an exact frequency."""
        if station is not None and frequency is not None:
            raise HTTPException(
                status_code=400, detail="Provide either station or frequency, not both"
            )

        if station is not None:
            if station not in app.station_cfgs:
                raise HTTPException(status_code=404, detail=f"Station not found: {station}")
            target_freq = float(app.station_cfgs[station].freq)
        elif frequency is not None:
            target_freq = frequency
        else:
            raise HTTPException(
                status_code=400, detail="Provide either station or frequency"
            )

        with app._lock:
            current_freq = app.state.freq

        app.tune(target_freq - current_freq)
        return _get_status()

    return fastapi_app
