# radio/scan_media.py
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path
from typing import Iterable, Optional

from mutagen.mp3 import MP3

from .db import connect
from .helpers import MediaInfo, upsert_media, upsert_station, link_station_media
from .station_config import StationConfig, load_station_toml


def parse_artist_title(filename: str) -> tuple[Optional[str], Optional[str]]:
    stem = Path(filename).stem.strip()
    if " - " in stem:
        a, t = stem.split(" - ", 1)
        return (a.strip() or None, t.strip() or None)
    return (None, stem or None)


def duration_s(path: Path) -> float:
    try:
        return float(MP3(path).info.length)
    except Exception:
        return 0.0


def iter_mp3(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for p in root.rglob("*.mp3"):
        if p.is_file():
            yield p


def scan_songs(con, music_root: str, *, verbose: bool) -> int:
    """Scan the music root for MP3 files and upsert them into the media table as songs."""
    root = Path(music_root).expanduser().resolve()
    n = 0
    for p in iter_mp3(root):
        tag = p.parent.name
        artist, title = parse_artist_title(p.name)
        mtime = int(p.stat().st_mtime)
        dur = duration_s(p)

        media_id = upsert_media(
            con,
            MediaInfo(
                path=str(p),
                kind="song",
                artist=artist,
                title=title,
                tag=tag,
                duration_s=dur,
                mtime=mtime,
            ),
        )
        if verbose:
            print(f"[song] {tag:>10}  {p.name}  ({dur:.1f}s)  id={media_id}")
        n += 1

    con.commit()
    return n


def scan_station_media_dir(con, station_id: int, directory: str, kind: str, *, verbose: bool) -> int:
    """Scan a directory for MP3s of the given kind and link them to the station."""
    if not directory:
        return 0

    d = Path(directory).expanduser().resolve()
    if not d.exists():
        return 0

    n = 0
    for p in iter_mp3(d):
        mtime = int(p.stat().st_mtime)
        dur = duration_s(p)
        media_id = upsert_media(
            con,
            MediaInfo(
                path=str(p),
                kind=kind,
                artist=None,
                title=p.stem,
                tag=None,
                duration_s=dur,
                mtime=mtime,
            ),
        )
        link_station_media(con, station_id, media_id)
        if verbose:
            print(f"[{kind:<10}] {p.name} ({dur:.1f}s) id={media_id} linked->station {station_id}")
        n += 1

    con.commit()
    return n


def scan_schedule_interstitials(
    con, station_id: int, cfg: StationConfig, *, verbose: bool
) -> dict[str, int]:
    """
    Scan all interstitial directories referenced in the schedule.
    Returns a dict mapping schedule_key -> count of files scanned.
    """
    results = {}
    seen_dirs: set[str] = set()

    for day, hour_map in cfg.schedule.items():
        for hour, entry in hour_map.items():
            if not entry.interstitials_dir or entry.interstitials_dir in seen_dirs:
                continue

            seen_dirs.add(entry.interstitials_dir)
            schedule_key = f"{day}-{hour}"

            con.execute(
                """
                INSERT INTO station_interstitials(
                    station_id, schedule_key, interstitials_dir, interstitials_probability
                )
                VALUES(?,?,?,?)
                ON CONFLICT(station_id, schedule_key) DO UPDATE SET
                    interstitials_dir=excluded.interstitials_dir,
                    interstitials_probability=excluded.interstitials_probability
                """,
                (station_id, schedule_key, entry.interstitials_dir, entry.interstitials_probability)
            )

            n = scan_station_media_dir(
                con, station_id, entry.interstitials_dir, "interstitial", verbose=verbose
            )
            results[schedule_key] = n

    return results


def load_station_cfgs(patterns: list[str]) -> list[StationConfig]:
    paths: list[str] = []
    for pat in patterns:
        expanded = glob.glob(pat)
        paths.extend(expanded if expanded else [pat])
    return [load_station_toml(p) for p in paths]


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan songs/idents/commercials into radio.db")
    ap.add_argument("--db", default="/home/radio/radio-code/radio.db")
    ap.add_argument("--music", required=True, help="Root containing tag subfolders (recursive)")
    ap.add_argument("--stations", nargs="+", required=True, help="Station TOML paths or globs")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    con = connect(str(Path(args.db).expanduser()))
    print(f"DB: {args.db}")

    print(f"Scanning songs under: {args.music}")
    n_songs = scan_songs(con, args.music, verbose=args.verbose)
    print(f"Songs: {n_songs}")

    cfgs = load_station_cfgs(args.stations)
    for cfg in cfgs:
        sid = upsert_station(con, cfg)
        print(f"Station upserted: {cfg.name} @ {cfg.freq:.1f} FM (id={sid})")

        n_idents = scan_station_media_dir(con, sid, cfg.idents_dir, "ident", verbose=args.verbose)
        n_commercials = scan_station_media_dir(con, sid, cfg.commercials_dir, "commercial", verbose=args.verbose)
        n_toth = scan_station_media_dir(con, sid, cfg.top_of_the_hour, "interstitial", verbose=args.verbose)
        print(f"  idents: {n_idents}")
        print(f"  commercials: {n_commercials}")
        print(f"  top_of_the_hour: {n_toth}")

        interstitial_counts = scan_schedule_interstitials(con, sid, cfg, verbose=args.verbose)
        if interstitial_counts:
            print(f"  interstitials:")
            for key, n in interstitial_counts.items():
                print(f"    {key}: {n}")

    con.commit()
    con.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
