# radio/api.py
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Optional

from fastapi import FastAPI, HTTPException

from . import helpers

if TYPE_CHECKING:
    from .radio import RadioApp


def _build_now_playing_and_up_next(
    con: Any, row: Any
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Build now_playing and up_next dicts from a station_state row."""
    if row is None or row["kind"] == "noise":
        return {"type": "noise"}, None

    now = time.time()

    media_row: Optional[Any] = None
    if row["current_media_id"] is not None:
        media_row = helpers.one(
            con,
            "SELECT artist, title FROM media WHERE id=?",
            (int(row["current_media_id"]),),
        )

    started_at = float(row["started_ts"]) if row["started_ts"] is not None else None
    ends_at = float(row["ends_ts"]) if row["ends_ts"] is not None else None
    duration_s = float(row["duration_s"]) if row["duration_s"] is not None else None

    now_playing: dict[str, Any] = {
        "type": row["kind"],
        "artist": media_row["artist"] if media_row else None,
        "title": media_row["title"] if media_row else None,
        "started_at": started_at,
        "ends_at": ends_at,
        "duration_s": duration_s,
        "elapsed_s": round(now - started_at, 3) if started_at is not None else None,
    }

    up_next: Optional[dict[str, Any]] = None
    queue_json = row["queue_json"]
    if queue_json is not None:
        try:
            queue = json.loads(queue_json)
            queue_index = int(row["queue_index"] or 0)
            if queue_index < len(queue):
                next_row = helpers.one(
                    con,
                    "SELECT kind, artist, title FROM media WHERE id=?",
                    (int(queue[queue_index]),),
                )
                if next_row:
                    up_next = {
                        "type": next_row["kind"],
                        "artist": next_row["artist"],
                        "title": next_row["title"],
                    }
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            pass

    return now_playing, up_next


def create_api(app: RadioApp) -> FastAPI:
    fastapi_app = FastAPI()

    @fastapi_app.get("/status")
    def status(station: Optional[str] = None) -> dict[str, Any]:
        # Read tuning state under lock
        with app._lock:
            dial_freq = app.state.freq
            current_station = app.state.station_name
            base_music_vol = app.state.base_music_vol

        if station is not None:
            # --- Station-specific query ---
            if station not in app.station_cfgs:
                raise HTTPException(status_code=404, detail=f"Station not found: {station}")

            target_freq = float(app.station_cfgs[station].freq)
            tuned = current_station == station and base_music_vol > 0

            base: dict[str, Any] = {
                "frequency": target_freq,
                "station": station,
                "tuned": tuned,
            }

            try:
                sid = helpers.station_id(app.con, station)
            except RuntimeError:
                return {**base, "now_playing": None, "up_next": None}

            row = helpers.get_station_state(app.con, sid)
            now_playing, up_next = _build_now_playing_and_up_next(app.con, row)
            return {**base, "now_playing": now_playing, "up_next": up_next}

        # --- Current tuning state ---
        tuned = base_music_vol > 0 and current_station is not None

        base = {
            "frequency": dial_freq,
            "station": current_station,
            "tuned": tuned,
        }

        if not tuned:
            return {**base, "now_playing": None, "up_next": None}

        try:
            sid = helpers.station_id(app.con, current_station)
        except RuntimeError:
            return {**base, "now_playing": None, "up_next": None}

        row = helpers.get_station_state(app.con, sid)
        now_playing, up_next = _build_now_playing_and_up_next(app.con, row)
        return {**base, "now_playing": now_playing, "up_next": up_next}

    return fastapi_app
