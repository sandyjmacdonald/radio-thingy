# radio/scheduler.py
from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .station_config import StationConfig, ScheduleEntry
from . import helpers


@dataclass(frozen=True)
class OverlayIdent:
    path: str
    at_s: float
    duck: float
    ramp_s: float


@dataclass(frozen=True)
class NowPlaying:
    station: str
    kind: str                  # song/ident/commercial/noise
    path: Optional[str]
    media_id: Optional[int]
    started_ts: float
    ends_ts: float
    seek_s: float
    slot_end_ts: float
    ident_overlay: Optional[OverlayIdent]


class Scheduler:
    """
    Behaviour:
      - Noise-only if no tags in current schedule slot
      - Continuity via station_state timestamps (seek when re-tuned)
      - Tick updates stations even when not tuned
      - Next selection logic:
          1) best-fit song with allowed tags whose duration <= (next slot start - now)
          2) else filler: ident + 0+ commercials to fill the gap (small overrun allowed)
      - Commercial breaks:
          - break_frequency_s: mark pending_break when elapsed
          - break runs after a song ends: ident + commercials ~ break_length_s
          - after break -> force ident overlay on next song
      - Station idents:
          - ident_frequency_s: if elapsed, overlay ident at start of next song (ident_pad_s)
          - overlay ducks music to ident_duck with ramp ident_ramp_s

    IMPORTANT:
      - Ident overlays are ONLY emitted (and consumed) when `active=True`
      - Idents must NOT “play late”: only schedule overlay when the song is starting now
    """

    def __init__(
        self,
        con,
        station_cfgs: dict[str, StationConfig],
        *,
        filler_slop_s: float = 4.0,
        break_slop_s: float = 4.0,
    ):
        self.con = con
        self.cfgs = station_cfgs
        self.filler_slop_s = float(filler_slop_s)
        self.break_slop_s = float(break_slop_s)

        helpers.ensure_station_state_queue_columns(con)

        for name in station_cfgs.keys():
            helpers.station_id(con, name)

        # Per-station RNG (de-sync stations even with identical libraries)
        self._rng: dict[str, random.Random] = {}
        run_entropy = int(time.time() * 1000)
        for name in station_cfgs.keys():
            h = hashlib.blake2b(name.encode("utf-8"), digest_size=8).digest()
            base = int.from_bytes(h, "big")
            self._rng[name] = random.Random(base ^ run_entropy)

        # Per-tick song reservation (reduce “same song at same time”)
        self._tick_reserved_song_ids: set[int] = set()

    # ----------------- Public -----------------

    def tick_all(self, now_ts: Optional[float] = None) -> None:
        now_ts = float(now_ts if now_ts is not None else time.time())
        self._tick_reserved_song_ids.clear()
        for name in self.cfgs.keys():
            self._maybe_mark_break_due(name, now_ts)
            # Background maintenance: NOT active -> no ident overlays emitted/consumed
            self.ensure_station_current(name, now_ts, active=False)

    def ensure_station_current(
        self,
        station_name: str,
        now_ts: Optional[float] = None,
        *,
        active: bool = False,
    ) -> NowPlaying:
        now_ts = float(now_ts if now_ts is not None else time.time())
        cfg = self.cfgs[station_name]
        sid = helpers.station_id(self.con, station_name)

        schedule_entry = self._schedule_entry_for_now(cfg, now_ts)
        tags = schedule_entry.tags
        slot_end_ts = self._next_slot_start_ts(now_ts)

        if not tags:
            helpers.set_noise_state(self.con, sid, now_ts, slot_end_ts)
            self.con.commit()
            return NowPlaying(
                station=station_name,
                kind="noise",
                path=None,
                media_id=None,
                started_ts=now_ts,
                ends_ts=slot_end_ts,
                seek_s=0.0,
                slot_end_ts=slot_end_ts,
                ident_overlay=None,
            )

        st = helpers.get_station_state(self.con, sid)

        # If current still valid, return it (with continuity seek)
        if st:
            kind = str(st["kind"] or "")
            ends = float(st["ends_ts"] or 0.0)
            if kind and kind != "noise" and ends > now_ts and st["path"]:
                started = float(st["started_ts"] or now_ts)
                seek = max(0.0, now_ts - started)

                ident_overlay = None
                # ONLY emit overlay idents when:
                #   - station is audible (active)
                #   - we're at the beginning of the song (not tuning mid-track)
                if kind == "song" and active and seek <= 0.25:
                    ident_overlay = self._ident_overlay_if_due(
                        station_name, cfg, sid, now_ts, st, consume=True
                    )

                return NowPlaying(
                    station=station_name,
                    kind=kind,
                    path=str(st["path"]),
                    media_id=int(st["current_media_id"]) if st["current_media_id"] is not None else None,
                    started_ts=started,
                    ends_ts=ends,
                    seek_s=seek,
                    slot_end_ts=slot_end_ts,
                    ident_overlay=ident_overlay,
                )

        np = self._advance_station(sid, station_name, cfg, tags, now_ts, slot_end_ts, active=active, schedule_entry=schedule_entry)
        self.con.commit()
        return np

    # ----------------- Advancement core -----------------

    def _advance_station(
        self,
        sid: int,
        station_name: str,
        cfg: StationConfig,
        tags: list[str],
        now_ts: float,
        slot_end_ts: float,
        *,
        active: bool,
        schedule_entry: Optional[ScheduleEntry] = None,
    ) -> NowPlaying:
        remaining = max(0.0, slot_end_ts - now_ts)
        st = helpers.get_station_state(self.con, sid)

        # Continue queue if present
        if st and st["queue_json"]:
            queue = json.loads(st["queue_json"])
            idx = int(st["queue_index"] or 0)
            if idx < len(queue):
                mid = int(queue[idx])
                item = helpers.media_by_id(self.con, mid)
                if item:
                    dur = float(item["duration_s"] or 0.0)
                    helpers.set_station_state(
                        self.con,
                        station_id_=sid,
                        media_id=mid,
                        kind=str(item["kind"]),
                        started_ts=now_ts,
                        ends_ts=now_ts + dur,
                        queue_json=json.dumps(queue),
                        queue_index=idx + 1,
                        pending_break=int(st["pending_break"] or 0),
                        last_break_ts=float(st["last_break_ts"] or 0.0),
                        force_ident_next=int(st["force_ident_next"] or 0),
                        last_ident_ts=float(st["last_ident_ts"] or 0.0),
                    )
                    helpers.insert_play(self.con, sid, mid, str(item["kind"]), now_ts)

                    ident_overlay = None
                    # Overlay only makes sense on a SONG start, and only if active/audible.
                    if active and str(item["kind"]) == "song":
                        ident_overlay = self._ident_overlay_if_due(
                            station_name, cfg, sid, now_ts, st, consume=True
                        )

                    return NowPlaying(
                        station=station_name,
                        kind=str(item["kind"]),
                        path=str(item["path"]),
                        media_id=mid,
                        started_ts=now_ts,
                        ends_ts=now_ts + dur,
                        seek_s=0.0,
                        slot_end_ts=slot_end_ts,
                        ident_overlay=ident_overlay,
                    )

            # queue exhausted -> clear
            helpers.update_station_flags(self.con, sid, queue_json=None, queue_index=0)

        pending_break = int(st["pending_break"] or 0) if st else 0
        last_break_ts = float(st["last_break_ts"] or 0.0) if st else 0.0
        force_ident_next = int(st["force_ident_next"] or 0) if st else 0
        last_ident_ts = float(st["last_ident_ts"] or 0.0) if st else 0.0

        # Break if pending
        if pending_break and int(cfg.break_length_s or 0) > 0:
            queue_ids = self._build_ident_plus_commercials_queue(
                station_name, sid, target_s=float(cfg.break_length_s), slop_s=self.break_slop_s
            )
            if queue_ids:
                first_id = int(queue_ids[0])
                item = helpers.media_by_id(self.con, first_id)
                dur = float(item["duration_s"] or 0.0) if item else 0.0

                helpers.set_station_state(
                    self.con,
                    station_id_=sid,
                    media_id=first_id,
                    kind=str(item["kind"]) if item else "ident",
                    started_ts=now_ts,
                    ends_ts=now_ts + dur,
                    queue_json=json.dumps(queue_ids),
                    queue_index=1,
                    pending_break=0,
                    last_break_ts=now_ts,
                    force_ident_next=1,   # after break, next SONG overlays ident
                    last_ident_ts=last_ident_ts,
                )
                helpers.insert_play(self.con, sid, first_id, str(item["kind"]) if item else "ident", now_ts)

                return NowPlaying(
                    station=station_name,
                    kind=str(item["kind"]) if item else "ident",
                    path=str(item["path"]) if item else None,
                    media_id=first_id,
                    started_ts=now_ts,
                    ends_ts=now_ts + dur,
                    seek_s=0.0,
                    slot_end_ts=slot_end_ts,
                    ident_overlay=None,
                )

            helpers.update_station_flags(self.con, sid, pending_break=0)

        # Best-fit song (seeded)
        song = self._pick_best_fit_song_station_seeded(
            station_name,
            tags=tags,
            max_duration=remaining,
            pool_limit=600,
            near_window_s=30.0,
            avoid_other_station_current=True,
            duration_jitter_s=12.0,
        )
        if song:
            mid = int(song["id"])
            self._tick_reserved_song_ids.add(mid)

            dur = float(song["duration_s"] or 0.0)
            
            # Check if we should queue an interstitial after this song
            queue_json = None
            queue_index = 0
            if schedule_entry and self._should_play_interstitial(station_name, schedule_entry):
                interstitial = self._pick_random_interstitial(sid, schedule_entry.interstitials_dir)
                if interstitial:
                    # Build queue: [song, interstitial]
                    queue_ids = [mid, int(interstitial["id"])]
                    queue_json = json.dumps(queue_ids)
                    queue_index = 1  # Next item will be the interstitial
            
            helpers.set_station_state(
                self.con,
                station_id_=sid,
                media_id=mid,
                kind="song",
                started_ts=now_ts,
                ends_ts=now_ts + dur,
                queue_json=queue_json,
                queue_index=queue_index,
                pending_break=0,
                last_break_ts=last_break_ts,
                force_ident_next=force_ident_next,
                last_ident_ts=last_ident_ts,
            )
            helpers.insert_play(self.con, sid, mid, "song", now_ts)

            # Only emit overlay if station is active/audible.
            st2 = helpers.get_station_state(self.con, sid) or {}
            ident_overlay = None
            if active:
                ident_overlay = self._ident_overlay_if_due(
                    station_name, cfg, sid, now_ts, st2, consume=True
                )

            return NowPlaying(
                station=station_name,
                kind="song",
                path=str(song["path"]),
                media_id=mid,
                started_ts=now_ts,
                ends_ts=now_ts + dur,
                seek_s=0.0,
                slot_end_ts=slot_end_ts,
                ident_overlay=ident_overlay,
            )

        # Filler (ident + commercials)
        queue_ids = self._build_ident_plus_commercials_queue(
            station_name, sid, target_s=remaining, slop_s=self.filler_slop_s
        )
        if not queue_ids:
            helpers.set_noise_state(self.con, sid, now_ts, slot_end_ts)
            return NowPlaying(
                station=station_name,
                kind="noise",
                path=None,
                media_id=None,
                started_ts=now_ts,
                ends_ts=slot_end_ts,
                seek_s=0.0,
                slot_end_ts=slot_end_ts,
                ident_overlay=None,
            )

        first_id = int(queue_ids[0])
        item = helpers.media_by_id(self.con, first_id)
        dur = float(item["duration_s"] or 0.0) if item else 0.0

        helpers.set_station_state(
            self.con,
            station_id_=sid,
            media_id=first_id,
            kind=str(item["kind"]) if item else "ident",
            started_ts=now_ts,
            ends_ts=now_ts + dur,
            queue_json=json.dumps(queue_ids),
            queue_index=1,
            pending_break=0,
            last_break_ts=last_break_ts,
            force_ident_next=force_ident_next,
            last_ident_ts=last_ident_ts,
        )
        helpers.insert_play(self.con, sid, first_id, str(item["kind"]) if item else "ident", now_ts)

        return NowPlaying(
            station=station_name,
            kind=str(item["kind"]) if item else "ident",
            path=str(item["path"]) if item else None,
            media_id=first_id,
            started_ts=now_ts,
            ends_ts=now_ts + dur,
            seek_s=0.0,
            slot_end_ts=slot_end_ts,
            ident_overlay=None,
        )

    # ----------------- Break/ident flags -----------------

    def _maybe_mark_break_due(self, station_name: str, now_ts: float) -> None:
        cfg = self.cfgs[station_name]
        freq = int(cfg.break_frequency_s or 0)
        if freq <= 0:
            return

        sid = helpers.station_id(self.con, station_name)
        st = helpers.get_station_state(self.con, sid)
        pending = int(st["pending_break"] or 0) if st else 0
        last_break_ts = float(st["last_break_ts"] or 0.0) if st else 0.0
        if pending:
            return
        if (now_ts - last_break_ts) >= freq:
            if st:
                helpers.update_station_flags(self.con, sid, pending_break=1)
            else:
                self.con.execute(
                    "INSERT OR IGNORE INTO station_state(station_id, pending_break, last_break_ts) VALUES(?,?,?)",
                    (sid, 1, last_break_ts),
                )
            self.con.commit()

    def _ident_overlay_if_due(
        self,
        station_name: str,
        cfg: StationConfig,
        sid: int,
        now_ts: float,
        st_row,
        *,
        consume: bool,
    ) -> Optional[OverlayIdent]:
        # If not consuming (i.e. not active/audible), do not emit an overlay
        if not consume:
            return None

        ident = helpers.random_station_media(self.con, sid, "ident")
        if not ident:
            return None

        force = int(st_row["force_ident_next"] or 0) if st_row else 0
        last_ident_ts = float(st_row["last_ident_ts"] or 0.0) if st_row else 0.0

        due = False
        if force:
            due = True
        else:
            freq = int(cfg.ident_frequency_s or 0)
            if freq > 0 and (now_ts - last_ident_ts) >= freq:
                due = True

        if not due:
            return None

        # Consume: clear force, stamp last_ident_ts
        helpers.update_station_flags(self.con, sid, force_ident_next=0, last_ident_ts=now_ts)
        self.con.commit()

        return OverlayIdent(
            path=str(ident["path"]),
            at_s=max(0.0, float(cfg.ident_pad_s or 0.0)),
            duck=max(0.0, min(1.0, float(cfg.ident_duck or 0.4))),
            ramp_s=max(0.0, float(cfg.ident_ramp_s or 0.5)),
        )

    # ----------------- De-sync song selection -----------------

    def _currently_playing_media_ids(self) -> set[int]:
        cur = self.con.execute(
            "SELECT current_media_id FROM station_state WHERE current_media_id IS NOT NULL"
        )
        return {int(r[0]) for r in cur.fetchall() if r[0] is not None}

    def _pick_best_fit_song_station_seeded(
        self,
        station_name: str,
        tags: list[str],
        max_duration: float,
        *,
        pool_limit: int = 600,
        near_window_s: float = 30.0,
        avoid_other_station_current: bool = True,
        duration_jitter_s: float = 12.0,
    ):
        rng = self._rng[station_name]

        max_duration = float(max_duration)
        if max_duration <= 1.0:
            return None

        tags = [str(t) for t in tags if t]
        if not tags:
            return None

        if duration_jitter_s > 0.0:
            max_duration = max(1.0, max_duration - rng.uniform(0.0, float(duration_jitter_s)))

        avoid_ids = set(self._tick_reserved_song_ids)
        if avoid_other_station_current:
            avoid_ids |= self._currently_playing_media_ids()

        placeholders = ",".join(["?"] * len(tags))
        sql = f"""
            SELECT id, path, duration_s
            FROM media
            WHERE kind='song'
              AND tag IN ({placeholders})
              AND duration_s IS NOT NULL
              AND duration_s <= ?
            ORDER BY duration_s DESC, id DESC
            LIMIT ?
        """
        rows = self.con.execute(sql, (*tags, max_duration, int(pool_limit))).fetchall()
        if not rows:
            return None

        filtered = [r for r in rows if int(r["id"]) not in avoid_ids]
        if filtered:
            rows = filtered

        best_dur = float(rows[0]["duration_s"] or 0.0)
        near = [r for r in rows if (best_dur - float(r["duration_s"] or 0.0)) <= float(near_window_s)]
        pick_from = near if len(near) >= 2 else rows[:20]

        return rng.choice(pick_from)

    # ----------------- Queue builders -----------------

    def _build_ident_plus_commercials_queue(
        self, station_name: str, sid: int, target_s: float, slop_s: float
    ) -> list[int]:
        target_s = max(0.0, float(target_s))
        max_total = target_s + float(slop_s)

        queue: list[int] = []
        total = 0.0

        ident = helpers.random_station_media(self.con, sid, "ident")
        if ident:
            queue.append(int(ident["id"]))
            total += float(ident["duration_s"] or 0.0)

        commercials = helpers.station_media_pool(self.con, sid, "commercial", limit=800)
        if not commercials:
            return queue

        commercials = list(commercials)
        self._rng[station_name].shuffle(commercials)

        for c in commercials:
            if total >= max_total:
                break
            dur = float(c["duration_s"] or 0.0)
            if dur <= 0.1:
                continue
            if (total + dur) <= max_total:
                queue.append(int(c["id"]))
                total += dur

        return queue

    # ----------------- Interstitial helpers -----------------

    def _should_play_interstitial(
        self, station_name: str, entry: ScheduleEntry
    ) -> bool:
        """
        Decide whether to play an interstitial based on probability.
        """
        if not entry.interstitials_dir or entry.interstitials_probability <= 0:
            return False
        
        # Roll the dice
        roll = self._rng[station_name].random()
        return roll < entry.interstitials_probability

    def _pick_random_interstitial(
        self, sid: int, interstitials_dir: str
    ) -> Optional:
        """
        Pick a random interstitial from the given directory for this station.
        """
        return helpers.random_station_media_filtered(
            self.con, sid, "interstitial", path_prefix=interstitials_dir
        )

    # ----------------- Schedule time helpers -----------------

    def _schedule_entry_for_now(self, cfg: StationConfig, now_ts: float) -> ScheduleEntry:
        """Get the schedule entry for the current time, or an empty entry if none."""
        dt = datetime.fromtimestamp(now_ts).astimezone()
        wd = dt.strftime("%A").lower()
        hr = int(dt.hour)
        entry = cfg.schedule.get(wd, {}).get(hr)
        if entry:
            return entry
        # Return empty entry if no schedule
        return ScheduleEntry(tags=[], interstitials_dir="", interstitials_probability=0.0)

    def _tags_for_now(self, cfg: StationConfig, now_ts: float) -> list[str]:
        """Get tags for the current time (convenience method for backward compatibility)."""
        return self._schedule_entry_for_now(cfg, now_ts).tags

    def _next_slot_start_ts(self, now_ts: float) -> float:
        dt = datetime.fromtimestamp(now_ts).astimezone()
        next_hour = dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return next_hour.timestamp()
