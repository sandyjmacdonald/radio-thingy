# radio/repo.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Any


@dataclass(frozen=True)
class MediaInfo:
    path: str
    kind: str               # song/commercial/ident/noise/interstitial
    artist: Optional[str]
    title: Optional[str]
    tag: Optional[str]
    duration_s: float
    mtime: int


# -------------------- generic query helpers --------------------

def one(con: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
    cur = con.execute(sql, params)
    return cur.fetchone()


def all_(con: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    cur = con.execute(sql, params)
    return cur.fetchall()


# -------------------- migrations for station_state --------------------

def ensure_station_state_queue_columns(con: sqlite3.Connection) -> None:
    cols = {r["name"] for r in con.execute("PRAGMA table_info(station_state)")}
    if "queue_json" not in cols:
        con.execute("ALTER TABLE station_state ADD COLUMN queue_json TEXT")
    if "queue_index" not in cols:
        con.execute("ALTER TABLE station_state ADD COLUMN queue_index INTEGER DEFAULT 0")
    if "last_ident_ts" not in cols:
        con.execute("ALTER TABLE station_state ADD COLUMN last_ident_ts REAL DEFAULT 0")
    con.commit()


# -------------------- media/station upserts --------------------

def upsert_media(con: sqlite3.Connection, info: MediaInfo) -> int:
    row = one(con, "SELECT id, mtime FROM media WHERE path=?", (info.path,))
    if row and int(row["mtime"] or 0) == info.mtime:
        return int(row["id"])

    con.execute(
        """
        INSERT INTO media(path, kind, artist, title, tag, duration_s, mtime)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
          kind=excluded.kind,
          artist=excluded.artist,
          title=excluded.title,
          tag=excluded.tag,
          duration_s=excluded.duration_s,
          mtime=excluded.mtime
        """,
        (info.path, info.kind, info.artist, info.title, info.tag, info.duration_s, info.mtime),
    )
    r2 = one(con, "SELECT id FROM media WHERE path=?", (info.path,))
    if not r2:
        raise RuntimeError(f"Failed to upsert media: {info.path}")
    return int(r2["id"])


def upsert_station(con: sqlite3.Connection, cfg: Any) -> int:
    """
    Expects cfg to have attributes:
      name, freq, idents_dir, commercials_dir,
      break_frequency_s, break_length_s,
      ident_frequency_s, ident_pad_s, ident_duck, ident_ramp_s
    """
    con.execute(
        """
        INSERT INTO stations(
          name, freq, idents_dir, commercials_dir,
          break_frequency_s, break_length_s,
          ident_frequency_s, ident_pad_s, ident_duck, ident_ramp_s
        )
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(name) DO UPDATE SET
          freq=excluded.freq,
          idents_dir=excluded.idents_dir,
          commercials_dir=excluded.commercials_dir,
          break_frequency_s=excluded.break_frequency_s,
          break_length_s=excluded.break_length_s,
          ident_frequency_s=excluded.ident_frequency_s,
          ident_pad_s=excluded.ident_pad_s,
          ident_duck=excluded.ident_duck,
          ident_ramp_s=excluded.ident_ramp_s
        """,
        (
            cfg.name,
            float(cfg.freq),
            str(cfg.idents_dir or ""),
            str(cfg.commercials_dir or ""),
            int(getattr(cfg, "break_frequency_s", 0) or 0),
            int(getattr(cfg, "break_length_s", 0) or 0),
            int(getattr(cfg, "ident_frequency_s", 0) or 0),
            float(getattr(cfg, "ident_pad_s", 0.0) or 0.0),
            float(getattr(cfg, "ident_duck", 0.4) or 0.4),
            float(getattr(cfg, "ident_ramp_s", 0.5) or 0.5),
        ),
    )
    row = one(con, "SELECT id FROM stations WHERE name=?", (cfg.name,))
    if not row:
        raise RuntimeError(f"Failed to upsert station: {cfg.name}")
    return int(row["id"])


def station_id(con: sqlite3.Connection, name: str) -> int:
    row = one(con, "SELECT id FROM stations WHERE name=?", (name,))
    if not row:
        raise RuntimeError(f"Station not in DB: {name} (run scan_media first)")
    return int(row["id"])


def link_station_media(con: sqlite3.Connection, station_id_: int, media_id: int) -> None:
    con.execute(
        "INSERT OR IGNORE INTO station_media(station_id, media_id) VALUES(?,?)",
        (int(station_id_), int(media_id)),
    )


# -------------------- station media queries --------------------

def random_station_media(con: sqlite3.Connection, station_id_: int, kind: str) -> Optional[sqlite3.Row]:
    return one(
        con,
        """
        SELECT m.id, m.path, m.kind, m.duration_s
        FROM media m
        JOIN station_media sm ON sm.media_id=m.id
        WHERE sm.station_id=? AND m.kind=?
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (int(station_id_), kind),
    )


def station_media_pool(con: sqlite3.Connection, station_id_: int, kind: str, limit: int = 500) -> list[sqlite3.Row]:
    return all_(
        con,
        """
        SELECT m.id, m.path, m.kind, m.duration_s
        FROM media m
        JOIN station_media sm ON sm.media_id=m.id
        WHERE sm.station_id=? AND m.kind=?
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (int(station_id_), kind, int(limit)),
    )


def media_by_id(con: sqlite3.Connection, media_id: int) -> Optional[sqlite3.Row]:
    return one(con, "SELECT id, path, kind, duration_s FROM media WHERE id=?", (int(media_id),))


def random_station_media_filtered(
    con: sqlite3.Connection, station_id_: int, kind: str, path_prefix: str
) -> Optional[sqlite3.Row]:
    """
    Get a random station media item of the given kind where path starts with path_prefix.
    Used for selecting interstitials from a specific directory.
    """
    return one(
        con,
        """
        SELECT m.id, m.path, m.kind, m.duration_s
        FROM media m
        JOIN station_media sm ON sm.media_id=m.id
        WHERE sm.station_id=? AND m.kind=? AND m.path LIKE ?
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (int(station_id_), kind, f"{path_prefix}%"),
    )


def best_fit_song(con: sqlite3.Connection, tags: list[str], max_duration: float, limit: int = 300) -> Optional[sqlite3.Row]:
    """
    Choose the song with allowed tag and duration <= max_duration that leaves smallest leftover.
    Random among near-ties.
    """
    if max_duration <= 1.0 or not tags:
        return None

    q = ",".join(["?"] * len(tags))
    rows = all_(
        con,
        f"""
        SELECT id, path, duration_s
        FROM media
        WHERE kind='song'
          AND tag IN ({q})
          AND duration_s IS NOT NULL
          AND duration_s > 1
          AND duration_s <= ?
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (*tags, float(max_duration), int(limit)),
    )
    if not rows:
        return None

    best_left = None
    best: list[sqlite3.Row] = []
    for r in rows:
        dur = float(r["duration_s"] or 0.0)
        left = max_duration - dur
        if left < 0:
            continue
        if best_left is None or left < best_left:
            best_left = left
            best = [r]
        elif abs(left - best_left) <= 1.5:
            best.append(r)

    import random
    return random.choice(best) if best else None


# -------------------- station_state helpers --------------------

def get_station_state(con: sqlite3.Connection, station_id_: int) -> Optional[sqlite3.Row]:
    return one(
        con,
        """
        SELECT
          ss.station_id,
          ss.current_media_id, ss.kind, ss.started_ts, ss.ends_ts,
          ss.queue_json, ss.queue_index,
          ss.pending_break, ss.last_break_ts, ss.force_ident_next, ss.last_ident_ts,
          m.path AS path, m.duration_s AS duration_s
        FROM station_state ss
        LEFT JOIN media m ON m.id = ss.current_media_id
        WHERE ss.station_id=?
        """,
        (int(station_id_),),
    )


def set_noise_state(con: sqlite3.Connection, station_id_: int, now_ts: float, ends_ts: float) -> None:
    con.execute(
        """
        INSERT INTO station_state(
          station_id, current_media_id, kind, started_ts, ends_ts,
          queue_json, queue_index
        )
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(station_id) DO UPDATE SET
          current_media_id=NULL,
          kind='noise',
          started_ts=excluded.started_ts,
          ends_ts=excluded.ends_ts,
          queue_json=NULL,
          queue_index=0
        """,
        (int(station_id_), None, "noise", float(now_ts), float(ends_ts), None, 0),
    )


def set_station_state(
    con: sqlite3.Connection,
    *,
    station_id_: int,
    media_id: int,
    kind: str,
    started_ts: float,
    ends_ts: float,
    queue_json: Optional[str],
    queue_index: int,
    pending_break: int,
    last_break_ts: float,
    force_ident_next: int,
    last_ident_ts: float,
) -> None:
    con.execute(
        """
        INSERT INTO station_state(
          station_id, current_media_id, kind, started_ts, ends_ts,
          queue_json, queue_index,
          pending_break, last_break_ts, force_ident_next, last_ident_ts
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(station_id) DO UPDATE SET
          current_media_id=excluded.current_media_id,
          kind=excluded.kind,
          started_ts=excluded.started_ts,
          ends_ts=excluded.ends_ts,
          queue_json=excluded.queue_json,
          queue_index=excluded.queue_index,
          pending_break=excluded.pending_break,
          last_break_ts=excluded.last_break_ts,
          force_ident_next=excluded.force_ident_next,
          last_ident_ts=excluded.last_ident_ts
        """,
        (
            int(station_id_),
            int(media_id),
            kind,
            float(started_ts),
            float(ends_ts),
            queue_json,
            int(queue_index),
            int(pending_break),
            float(last_break_ts),
            int(force_ident_next),
            float(last_ident_ts),
        ),
    )


def update_station_flags(
    con: sqlite3.Connection,
    station_id_: int,
    *,
    pending_break: Optional[int] = None,
    last_break_ts: Optional[float] = None,
    force_ident_next: Optional[int] = None,
    last_ident_ts: Optional[float] = None,
    queue_json: Optional[str] = None,
    queue_index: Optional[int] = None,
) -> None:
    sets = []
    params: list[Any] = []
    if pending_break is not None:
        sets.append("pending_break=?"); params.append(int(pending_break))
    if last_break_ts is not None:
        sets.append("last_break_ts=?"); params.append(float(last_break_ts))
    if force_ident_next is not None:
        sets.append("force_ident_next=?"); params.append(int(force_ident_next))
    if last_ident_ts is not None:
        sets.append("last_ident_ts=?"); params.append(float(last_ident_ts))
    if queue_json is not None:
        sets.append("queue_json=?"); params.append(queue_json)
    if queue_index is not None:
        sets.append("queue_index=?"); params.append(int(queue_index))

    if not sets:
        return

    params.append(int(station_id_))
    con.execute(f"UPDATE station_state SET {', '.join(sets)} WHERE station_id=?", params)


def insert_play(con: sqlite3.Connection, station_id_: int, media_id: int, kind: str, started_ts: float) -> None:
    con.execute(
        """
        INSERT INTO plays(station_id, media_id, kind, started_ts, ended_ts)
        VALUES(?,?,?,?,NULL)
        """,
        (int(station_id_), int(media_id), kind, float(started_ts)),
    )
