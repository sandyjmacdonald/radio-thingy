#!/usr/bin/env python3
"""
rescan.py — nuke the DB and rerun the scan_media CLI.

Usage:
  . .venv/bin/activate
  python rescan.py

Optional:
  python rescan.py --db ./radio.db --music ~/media/music --stations "./stations/*.toml" --verbose
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def expand(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="./radio.db", help="Path to SQLite DB (default: ./radio.db)")
    ap.add_argument("--music", default="~/media/music", help="Music root directory (default: ~/media/music)")
    ap.add_argument("--stations", default="./stations/*.toml", help='Station TOML glob (default: ./stations/*.toml)')
    ap.add_argument("--verbose", action="store_true", help="Pass --verbose to scan_media")
    args = ap.parse_args()

    db_path = Path(expand(args.db))
    music_root = expand(args.music)
    stations_glob = args.stations

    # Nuke DB
    if db_path.exists():
        print(f"Deleting DB: {db_path}")
        db_path.unlink()

    # Re-run scan using the module CLI (no brittle imports)
    cmd = [
        sys.executable,
        "-m",
        "radio.scan_media",
        "--db",
        str(db_path),
        "--music",
        music_root,
        "--stations",
        stations_glob,
    ]
    if args.verbose:
        cmd.append("--verbose")

    print("Running:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
