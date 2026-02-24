# radio/api.py
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Optional

from fastapi import FastAPI

from . import helpers

if TYPE_CHECKING:
    from .radio import RadioApp


def create_api(app: RadioApp) -> FastAPI:
    fastapi_app = FastAPI()

    @fastapi_app.get("/status")
    def status() -> dict[str, Any]:
        # 1. Read tuning state under lock
        with app._lock:
            freq = app.state.freq
            station_name = app.state.station_name
            base_music_vol = app.state.base_music_vol

        tuned = base_music_vol > 0 and station_name is not None

        base: dict[str, Any] = {
            "frequency": freq,
            "station": station_name,
            "tuned": tuned,
        }

        # 2. Not tuned
        if not tuned:
            return {**base, "now_playing": None, "up_next": None}

        # 3. Look up station id
        try:
            sid = helpers.station_id(app.con, station_name)
        except RuntimeError:
            return {**base, "now_playing": None, "up_next": None}

        # 4. Get station state
        row = helpers.get_station_state(app.con, sid)

        # 5. Noise or no state
        if row is None or row["kind"] == "noise":
            return {**base, "now_playing": {"type": "noise"}, "up_next": None}

        # 6. Build now_playing
        now = time.time()

        media_row: Optional[Any] = None
        if row["current_media_id"] is not None:
            media_row = helpers.one(
                app.con,
                "SELECT artist, title FROM media WHERE id=?",
                (int(row["current_media_id"]),),
            )

        artist = media_row["artist"] if media_row else None
        title = media_row["title"] if media_row else None
        started_at = float(row["started_ts"]) if row["started_ts"] is not None else None
        ends_at = float(row["ends_ts"]) if row["ends_ts"] is not None else None
        duration_s = float(row["duration_s"]) if row["duration_s"] is not None else None
        elapsed_s = round(now - started_at, 3) if started_at is not None else None

        now_playing: dict[str, Any] = {
            "type": row["kind"],
            "artist": artist,
            "title": title,
            "started_at": started_at,
            "ends_at": ends_at,
            "duration_s": duration_s,
            "elapsed_s": elapsed_s,
        }

        # 7. Build up_next
        up_next: Optional[dict[str, Any]] = None
        queue_json = row["queue_json"]
        if queue_json is not None:
            try:
                queue = json.loads(queue_json)
                queue_index = int(row["queue_index"] or 0)
                if queue_index < len(queue):
                    next_id = queue[queue_index]
                    next_row = helpers.one(
                        app.con,
                        "SELECT kind, artist, title FROM media WHERE id=?",
                        (int(next_id),),
                    )
                    if next_row:
                        up_next = {
                            "type": next_row["kind"],
                            "artist": next_row["artist"],
                            "title": next_row["title"],
                        }
            except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                pass

        return {**base, "now_playing": now_playing, "up_next": up_next}

    return fastapi_app
