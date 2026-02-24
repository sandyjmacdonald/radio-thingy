# radio/db.py
from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS media (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL CHECK(kind IN ('song','commercial','ident','noise','interstitial')),
  artist TEXT,
  title TEXT,
  tag TEXT,
  duration_s REAL,
  mtime INTEGER
);

CREATE TABLE IF NOT EXISTS stations (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  freq REAL NOT NULL,
  idents_dir TEXT,
  commercials_dir TEXT,
  break_frequency_s INTEGER DEFAULT 0,
  break_length_s INTEGER DEFAULT 0,
  ident_frequency_s INTEGER DEFAULT 0,
  ident_pad_s REAL DEFAULT 0,
  ident_duck REAL DEFAULT 0.4,
  ident_ramp_s REAL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS station_media (
  station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
  media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  PRIMARY KEY (station_id, media_id)
);

CREATE TABLE IF NOT EXISTS plays (
  id INTEGER PRIMARY KEY,
  station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
  media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  started_ts REAL NOT NULL,
  ended_ts REAL
);

CREATE TABLE IF NOT EXISTS station_state (
  station_id INTEGER PRIMARY KEY REFERENCES stations(id) ON DELETE CASCADE,
  current_media_id INTEGER REFERENCES media(id),
  kind TEXT,
  started_ts REAL,
  ends_ts REAL,

  queue_json TEXT,
  queue_index INTEGER DEFAULT 0,

  pending_break INTEGER DEFAULT 0,
  last_break_ts REAL DEFAULT 0,
  force_ident_next INTEGER DEFAULT 0,
  last_ident_ts REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS station_interstitials (
  id INTEGER PRIMARY KEY,
  station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
  schedule_key TEXT NOT NULL,
  interstitials_dir TEXT NOT NULL,
  interstitials_probability REAL DEFAULT 0.0,
  UNIQUE(station_id, schedule_key)
);

CREATE INDEX IF NOT EXISTS idx_media_kind_tag ON media(kind, tag);
CREATE INDEX IF NOT EXISTS idx_media_song_tag_dur ON media(kind, tag, duration_s);
CREATE INDEX IF NOT EXISTS idx_plays_station_time ON plays(station_id, started_ts);
"""

def _ensure_column(con: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

def connect(db_path: str) -> sqlite3.Connection:
    """Open (or create) the database at db_path, apply the schema, and run column migrations."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)

    # Migrations for older DBs that predate the current schema
    _ensure_column(con, "station_state", "queue_json", "TEXT")
    _ensure_column(con, "station_state", "queue_index", "INTEGER DEFAULT 0")
    _ensure_column(con, "station_state", "last_ident_ts", "REAL DEFAULT 0")
    con.commit()

    return con
