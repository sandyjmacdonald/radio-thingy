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
  kind TEXT NOT NULL CHECK(kind IN ('song','commercial','ident','noise','overlay','top_of_hour')),
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
  overlay_pad_s REAL DEFAULT 0,
  overlay_duck REAL DEFAULT 0.4,
  overlay_ramp_s REAL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS station_media (
  station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
  media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  last_played_ts REAL DEFAULT 0,
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
  last_ident_ts REAL DEFAULT 0,
  last_toth_slot_ts REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS station_overlays (
  id INTEGER PRIMARY KEY,
  station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
  schedule_key TEXT NOT NULL,
  overlays_dir TEXT NOT NULL,
  overlays_probability REAL DEFAULT 0.0,
  UNIQUE(station_id, schedule_key)
);

CREATE INDEX IF NOT EXISTS idx_media_kind_tag ON media(kind, tag);
CREATE INDEX IF NOT EXISTS idx_media_song_tag_dur ON media(kind, tag, duration_s);
CREATE INDEX IF NOT EXISTS idx_plays_station_time ON plays(station_id, started_ts);
CREATE INDEX IF NOT EXISTS idx_station_media_last_played ON station_media(station_id, last_played_ts);
"""

def _ensure_column(con: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

def _migrate_media_kinds(con: sqlite3.Connection) -> None:
    """Recreate media table replacing kind='interstitial' with 'overlay'/'top_of_hour'."""
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='media'"
    ).fetchone()
    if not row or "'interstitial'" not in (row["sql"] or ""):
        return
    con.executescript("""
        PRAGMA foreign_keys=OFF;
        ALTER TABLE media RENAME TO _media_migrate;
        CREATE TABLE media (
          id INTEGER PRIMARY KEY,
          path TEXT NOT NULL UNIQUE,
          kind TEXT NOT NULL CHECK(kind IN ('song','commercial','ident','noise','overlay','top_of_hour')),
          artist TEXT,
          title TEXT,
          tag TEXT,
          duration_s REAL,
          mtime INTEGER
        );
        INSERT INTO media(id, path, kind, artist, title, tag, duration_s, mtime)
        SELECT id, path,
               CASE WHEN kind = 'interstitial' THEN 'overlay' ELSE kind END,
               artist, title, tag, duration_s, mtime
        FROM _media_migrate;
        DROP TABLE _media_migrate;
        PRAGMA foreign_keys=ON;
    """)

def _migrate_stations_overlay_columns(con: sqlite3.Connection) -> None:
    """Add overlay_pad_s/overlay_duck/overlay_ramp_s columns, copying from old ident_ columns."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(stations)")}
    if "overlay_pad_s" not in cols:
        con.execute("ALTER TABLE stations ADD COLUMN overlay_pad_s REAL DEFAULT 0")
        if "ident_pad_s" in cols:
            con.execute("UPDATE stations SET overlay_pad_s = ident_pad_s")
    if "overlay_duck" not in cols:
        con.execute("ALTER TABLE stations ADD COLUMN overlay_duck REAL DEFAULT 0.4")
        if "ident_duck" in cols:
            con.execute("UPDATE stations SET overlay_duck = ident_duck")
    if "overlay_ramp_s" not in cols:
        con.execute("ALTER TABLE stations ADD COLUMN overlay_ramp_s REAL DEFAULT 0.5")
        if "ident_ramp_s" in cols:
            con.execute("UPDATE stations SET overlay_ramp_s = ident_ramp_s")

def _migrate_station_interstitials_table(con: sqlite3.Connection) -> None:
    """Rename station_interstitials to station_overlays and update column names."""
    tables = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "station_interstitials" in tables and "station_overlays" not in tables:
        con.execute("ALTER TABLE station_interstitials RENAME TO station_overlays")
    if "station_overlays" in tables or "station_interstitials" not in tables:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(station_overlays)")} if "station_overlays" in tables else set()
        if "interstitials_dir" in cols and "overlays_dir" not in cols:
            con.execute("ALTER TABLE station_overlays RENAME COLUMN interstitials_dir TO overlays_dir")
        if "interstitials_probability" in cols and "overlays_probability" not in cols:
            con.execute("ALTER TABLE station_overlays RENAME COLUMN interstitials_probability TO overlays_probability")

def connect(db_path: str) -> sqlite3.Connection:
    """Open (or create) the database at db_path, apply the schema, and run column migrations."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row

    # Pre-migration: if station_media already exists without last_played_ts, add it
    # now so that executescript(SCHEMA) can create the index on that column.
    tables = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "station_media" in tables:
        _ensure_column(con, "station_media", "last_played_ts", "REAL DEFAULT 0")

    con.executescript(SCHEMA)

    # Migrations for older DBs that predate the current schema
    _ensure_column(con, "station_state", "queue_json", "TEXT")
    _ensure_column(con, "station_state", "queue_index", "INTEGER DEFAULT 0")
    _ensure_column(con, "station_state", "last_ident_ts", "REAL DEFAULT 0")
    _ensure_column(con, "station_state", "last_toth_slot_ts", "REAL DEFAULT 0")
    _ensure_column(con, "station_media", "last_played_ts", "REAL DEFAULT 0")

    _migrate_media_kinds(con)
    _migrate_stations_overlay_columns(con)
    _migrate_station_interstitials_table(con)

    con.commit()

    return con
