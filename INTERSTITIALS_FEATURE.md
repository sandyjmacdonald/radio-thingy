# Interstitials Feature

## Overview

Interstitials are short audio clips that can play between songs on a per-station, per-tag basis. They are configured in the station's schedule and can be given a probability between 0 and 1 that governs whether they play or not.

## Configuration

### Station TOML Configuration

In your station's TOML file (e.g., `stations/KHHZ.toml`), you can now specify interstitials for each schedule entry:

```toml
[schedule.monday]
7 = { tags = "pop", interstitials = "/home/radio/media/interstitials/KHHZ-pop", interstitials_probability = 0.3 }
8 = { tags = "pop", interstitials = "/home/radio/media/interstitials/KHHZ-pop", interstitials_probability = 1.0 }
9 = { tags = "pop" }  # No interstitials for this hour
```

### Parameters

- **`interstitials`**: The directory path where interstitial MP3 files are located
- **`interstitials_probability`**: A float between 0.0 and 1.0
  - `0.0` = never play interstitials
  - `1.0` = play an interstitial after every song
  - `0.3` = 30% chance of playing an interstitial after each song

## Directory Structure

Place your interstitial MP3 files in directories organized by station and tag:

```
/home/radio/media/interstitials/
├── KHHZ-pop/
│   ├── promo1.mp3
│   ├── promo2.mp3
│   └── announcement.mp3
├── KHHZ-rock/
│   ├── rock-promo1.mp3
│   └── rock-promo2.mp3
└── KHMR-jazz/
    ├── jazz-intro.mp3
    └── jazz-outro.mp3
```

## Scanning Media

After adding interstitials to your station configuration, run the media scanner to index them:

```bash
python -m radio.scan_media \
  --db /path/to/radio.db \
  --music /path/to/music \
  --stations stations/*.toml \
  --verbose
```

The scanner will:
1. Scan all MP3 files in the specified interstitials directories
2. Store them in the database with `kind='interstitial'`
3. Link them to the appropriate station
4. Display output like:
   ```
   Station upserted: KHHZ @ 92.5 FM (id=1)
     idents: seen=10, scanned=10
     commercials: seen=5, scanned=5
     interstitials:
       monday-7: seen=3, scanned=3
       monday-8: seen=3, scanned=3
   ```

## How It Works

1. **Scheduler Decision**: When the scheduler selects a song to play, it checks the current schedule entry's interstitials configuration
2. **Probability Roll**: It uses the station's random number generator to roll a dice against the `interstitials_probability`
3. **Queue Building**: If the roll succeeds, it picks a random interstitial from the specified directory and queues it after the song
4. **Playback**: The song plays first, then the interstitial plays automatically

## Database Changes

The implementation adds:

1. **New media kind**: `'interstitial'` added to the `media.kind` CHECK constraint
2. **New table**: `station_interstitials` to track interstitial configurations per schedule entry
3. **Schema**:
   ```sql
   CREATE TABLE IF NOT EXISTS station_interstitials (
     id INTEGER PRIMARY KEY,
     station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
     schedule_key TEXT NOT NULL,
     interstitials_dir TEXT NOT NULL,
     interstitials_probability REAL DEFAULT 0.0,
     UNIQUE(station_id, schedule_key)
   );
   ```

## Code Changes Summary

### 1. `radio/station_config.py`
- Added `ScheduleEntry` dataclass with `tags`, `interstitials_dir`, and `interstitials_probability`
- Updated `_normalize_schedule()` to parse interstitial configuration from TOML
- Changed schedule type from `dict[str, dict[int, list[str]]]` to `dict[str, dict[int, ScheduleEntry]]`

### 2. `radio/db.py`
- Added `'interstitial'` to media kind CHECK constraint
- Added `station_interstitials` table to schema

### 3. `radio/helpers.py`
- Added `random_station_media_filtered()` function to query interstitials by directory path
- Updated `MediaInfo` comment to include 'interstitial' kind

### 4. `radio/scan_media.py`
- Added `scan_schedule_interstitials()` function to scan interstitial directories
- Updated `main()` to call the new scanning function for each station

### 5. `radio/scheduler.py`
- Added `_schedule_entry_for_now()` to get full schedule entry (not just tags)
- Added `_should_play_interstitial()` to check probability
- Added `_pick_random_interstitial()` to select a random interstitial
- Updated `_advance_station()` to optionally queue interstitials after songs
- Updated `ensure_station_current()` to pass schedule entry to advance function

## Example Usage

```toml
# stations/KHHZ.toml
name = "KHHZ"
freq = 92.5

idents_dir = "/home/radio/media/idents/KHHZ"
commercials_dir = "/home/radio/media/commercials"

break_frequency_s = 900
break_length_s = 60

ident_frequency_s = 180
ident_pad_s = 2.0

[schedule.monday]
# Morning drive - frequent promos
7 = { tags = "pop", interstitials = "/home/radio/media/interstitials/KHHZ-morning", interstitials_probability = 0.5 }
8 = { tags = "pop", interstitials = "/home/radio/media/interstitials/KHHZ-morning", interstitials_probability = 0.5 }

# Midday - occasional promos
12 = { tags = "pop", interstitials = "/home/radio/media/interstitials/KHHZ-midday", interstitials_probability = 0.2 }

# Evening - different content, always play
18 = { tags = "rock", interstitials = "/home/radio/media/interstitials/KHHZ-evening", interstitials_probability = 1.0 }

# Late night - no interstitials
23 = { tags = "pop" }
```

## Notes

- Interstitials are selected randomly from the specified directory
- The same directory can be used for multiple schedule entries
- Each station has its own random number generator, so stations won't sync up
- Interstitials play seamlessly between songs using the queue system
- The probability is checked fresh for each song, so it's truly random

