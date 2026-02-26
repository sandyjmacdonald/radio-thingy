# Radio Thingy 📻

A Python-based FM radio station emulator that brings the nostalgic experience of classic FM radio to your Raspberry Pi. Tune between multiple stations, each with its own frequency, programming schedule, station identifications, interstitials, and commercial breaks.

## Overview

Radio Thingy simulates a complete FM radio ecosystem with multiple stations broadcasting on different frequencies. Each station can have its own 24/7 programming schedule, mixing music with authentic radio station elements like idents (station identifications), interstitials (promos and announcements), and commercial breaks.

Experience the joy of tuning through static between stations, catching your favourite music, and hearing those classic radio elements that made FM radio so engaging.

## Features

### 🎵 Multiple Radio Stations
- Configure multiple stations, each with unique call letters and FM frequencies
- Realistic inter-station static/noise when tuning
- Independent programming and schedules per station

### 📅 Flexible Scheduling
- 24/7 programming schedules with hourly granularity
- Different schedules for each day of the week
- Mix multiple music genres within a single hour
- Tag-based music selection from your library

### 🎙️ Station Identifications (Idents)
- Periodic station identification overlays
- Customisable frequency and timing
- Audio ducking — music volume reduces during ident playback
- Configurable fade in/out for smooth transitions

### 🎬 Interstitials
- Play short promotional clips between songs
- Configure per hour and per music tag
- Adjustable probability (0.0 to 1.0) for how often they play
- Perfect for "Now playing your favourite rock hits!" style announcements

### ⏰ Top-of-the-Hour Jingles

A single MP3 (chosen at random from a directory) plays as the very first item whenever a new hour slot begins. Unlike interstitials, there is no probability gate — the jingle always plays. Configure the directory with `top_of_the_hour` in your station TOML.

### 📢 Commercial Breaks
- Scheduled commercial breaks at configurable intervals
- Automatic break construction (ident + commercials)
- Target length with intelligent media selection
- Automatic return to music after breaks

### 🎚️ Audio Features
- Seamless continuity when switching stations
- MPV-based playback for reliable audio
- Support for external DACs and amplifiers
- Background noise loop for authentic radio feel

### 🔧 Smart Scheduler
- Intelligent song selection based on duration to fit time slots
- Avoids playing the same song on multiple stations simultaneously
- Per-station seeded randomisation for variety
- Queue system for seamless playback of breaks and interstitials

## Hardware Requirements

### Minimum Setup
- **Raspberry Pi** (any model with audio output)
  - Raspberry Pi 3/4/5 recommended for best performance
  - Raspberry Pi Zero 2 W works but may be slower
- **Speaker(s)** connected via:
  - 3.5mm audio jack (built-in)
  - HDMI audio output
  - USB audio interface
  - HAT with audio output

### Recommended Setup
- **Raspberry Pi 4 or 5** (better audio quality and performance)
- **External DAC/Amplifier** for improved audio quality
  - HiFiBerry DAC+ or similar
  - USB DAC
  - I2S DAC HAT
- **Quality speakers or headphones**

## Installation

### 1. Clone the Repository

```bash
git clone <your-repo-url> radio-thingy
cd radio-thingy
```

### 2. Run the Installation Script

```bash
chmod +x install.sh
./install.sh
```

This will:
- Install system dependencies (Python 3, mpv, etc.)
- Create a Python virtual environment
- Install required Python packages

### 3. Activate the Virtual Environment

```bash
source .venv/bin/activate
```

## Configuration

### Runtime Configuration (`config.toml`)

All runtime settings live in a single TOML file. Copy the provided example and edit the paths:

```bash
cp config.toml.example config.toml
```

The three keys are **required**; everything else has a sensible default:

| Key | Required | Default | Description |
|---|---|---|---|
| `db_path` | ✓ | — | Path to the SQLite database |
| `station_tomls_glob` | ✓ | — | Glob pattern for station TOML files |
| `noise_file` | ✓ | — | Path to the inter-station static/noise MP3 |
| `audio_device` | | `"pipewire"` | MPV audio output device |
| `master_vol` | | `60` | Global master volume, 0–100 |
| `radio_af` | | `null` | Optional MPV `--af` filter chain for radio processing |
| `freq_min` | | `88.0` | Lower bound of the dial in MHz |
| `freq_max` | | `98.0` | Upper bound of the dial in MHz |
| `step` | | `0.1` | MHz per button press |
| `lock_window` | | `0.2` | MHz from a station centre → full volume |
| `fade_window` | | `0.5` | MHz fade zone outside `lock_window` |
| `tick_s` | | `0.25` | Main loop tick interval in seconds |
| `api_host` | | `"0.0.0.0"` | HTTP API bind address |
| `api_port` | | `8000` | HTTP API port |

See `config.toml.example` for the full file with inline comments.

### Directory Structure

Organise your media files as follows:

```
/path/to/media/
├── music/                    # Your music library
│   ├── pop/                  # Genre/tag subdirectories
│   │   ├── Artist - Song1.mp3
│   │   └── Artist - Song2.mp3
│   ├── rock/
│   ├── jazz/
│   └── ...
├── idents/                   # Station identifications
│   ├── MYCALL/
│   │   ├── ident1.mp3
│   │   └── ident2.mp3
│   └── OTHERCALL/
│       └── ident.mp3
├── commercials/              # Commercial/advertisement files
│   ├── MYCALL/
│   │   ├── ad1.mp3
│   │   └── ad2.mp3
│   └── shared/
│       └── generic-ad.mp3
├── toth/                     # Top-of-the-hour jingles
│   ├── MYCALL/
│   │   ├── toth1.mp3
│   │   └── toth2.mp3
│   └── OTHERCALL/
│       └── toth.mp3
└── interstitials/            # Promotional clips
    ├── morning/
    │   ├── morning-show-promo.mp3
    │   └── wake-up-message.mp3
    ├── evening/
    │   └── drive-time-intro.mp3
    └── weekend/
        └── weekend-special.mp3
```

### Station Configuration

Create a station configuration file for each station:

```bash
cp stations/station.toml.example stations/MYCALL.toml
```

Edit the file to configure your station:

```toml
name = "MYCALL"
freq = 99.9

idents_dir = "/path/to/media/idents/MYCALL"
commercials_dir = "/path/to/media/commercials/MYCALL"

break_frequency_s = 900    # Commercial break every 15 minutes
break_length_s = 60        # 60-second breaks

ident_frequency_s = 180    # Station ID every 3 minutes
ident_pad_s = 2.0          # Start 2 seconds into the song
ident_duck = 0.4           # Reduce music to 40% during ident
ident_ramp_s = 0.5         # 0.5 second fade

[schedule.monday]
# Morning drive - frequent promos
7 = { tags = "pop", interstitials = "/path/to/interstitials/morning", interstitials_probability = 0.5 }
8 = { tags = "pop", interstitials = "/path/to/interstitials/morning", interstitials_probability = 0.5 }

# Midday - occasional promos
12 = { tags = "pop", interstitials = "/path/to/interstitials/midday", interstitials_probability = 0.2 }

# Evening - different content, always play
18 = { tags = "rock", interstitials = "/path/to/interstitials/evening", interstitials_probability = 1.0 }

# Late night - no interstitials
23 = { tags = "pop" }
```

#### Interstitial Schedule Parameters

- **`interstitials`**: Directory path containing the interstitial MP3 files for this hour
- **`interstitials_probability`**: Float between `0.0` and `1.0` controlling how often they play
  - `0.0` — never play interstitials
  - `0.3` — 30% chance of playing one after each song
  - `1.0` — play an interstitial after every song

See `stations/station.toml.example` for a complete example with detailed comments.

### Scanning Media

After configuring your station(s), scan your media library:

```bash
python -m radio.scan_media \
  --db /path/to/radio.db \
  --music /path/to/media/music \
  --stations stations/*.toml \
  --verbose
```

This will:
- Index all MP3 files in your music library
- Scan station idents and commercials
- Scan interstitials from schedule configurations
- Build the database for playback

You can rescan any time you add new media files.

## Usage

### Starting the Radio

```bash
python play_radio.py
```

`play_radio.py` is the sole entry point. It reads `CONFIG_PATH` (set to `/home/radio/radio-code/config.toml` by default — edit the constant at the top of the file to match your setup), then wires up the GPIO buttons and starts the radio.

The radio will start playing with:
- Initial station tuned to the first configured station
- Appropriate programming based on current time
- Background tick updating all stations

To run without GPIO (e.g. for API-only use on a non-Pi machine), you can instantiate `RadioApp` directly with no inputs:

```python
from radio.config import load_config
from radio.radio import RadioApp

app = RadioApp(config=load_config("config.toml"), inputs=[])
app.run()
```

## HTTP API

When the radio starts, a FastAPI server starts automatically on port `8000`. All endpoints are read-only except `/tune`.

### `GET /stations`

Returns all configured stations sorted by frequency.

```bash
curl http://localhost:8000/stations
```

```json
[
  { "name": "KHHZ", "frequency": 92.5 },
  { "name": "WXYZ", "frequency": 95.1 }
]
```

---

### `GET /status`

Returns the current state of the dial — what is playing and what is queued next.

```bash
curl http://localhost:8000/status
```

```json
{
  "frequency": 92.5,
  "station": "KHHZ",
  "tuned": true,
  "now_playing": {
    "type": "song",
    "artist": "The Beatles",
    "title": "Let It Be",
    "started_at": 1234567890.123,
    "ends_at": 1234567950.456,
    "duration_s": 243.5,
    "elapsed_s": 60.3
  },
  "up_next": {
    "type": "interstitial",
    "artist": null,
    "title": "Morning Promo"
  }
}
```

| Field | Description |
|---|---|
| `frequency` | Current dial frequency in MHz |
| `station` | Name of the nearest station |
| `tuned` | `true` when the dial is close enough to a station to hear it |
| `now_playing` | `null` when not tuned; `{"type": "noise"}` when tuned to static; full object when playing |
| `up_next` | Next item already in the queue, or `null` if nothing is queued yet |
| `type` | One of: `song`, `interstitial`, `commercial`, `ident`, `noise` |
| `elapsed_s` | Seconds since the current track started, computed at request time |

**Optional `?station=` parameter**

Pass a station name to query any station regardless of what is currently tuned:

```bash
curl "http://localhost:8000/status?station=WXYZ"
```

This always returns `now_playing` and `up_next` for the named station. `tuned` reflects whether the dial is actually on that station. Returns `404` for unknown station names.

---

### `POST /tune`

Moves the dial to a station by name or to a specific frequency. Returns the updated `/status` response.

**Tune to a station by name:**

```bash
curl -X POST "http://localhost:8000/tune?station=KHHZ"
```

**Tune to a frequency:**

```bash
curl -X POST "http://localhost:8000/tune?frequency=92.5"
```

Passing both `station` and `frequency` in the same request returns `400`. An unknown station name returns `404`. Frequencies are clamped to the configured dial range.

---

## Key Concepts

### Tags and Music Selection

Music files are organised by tags (genres/categories). The tag is determined by the parent directory name:

```
music/
├── pop/            # Tag: "pop"
├── rock/           # Tag: "rock"
└── jazz/           # Tag: "jazz"
```

Station schedules specify which tags to play each hour:

```toml
7 = { tags = "pop" }                    # Only pop music
8 = { tags = ["pop", "rock"] }          # Mix of pop and rock
```

### Interstitials

Interstitials are short audio clips (typically 5–30 seconds) that play between songs. They're perfect for:
- "You're listening to MYCALL, 99.9 FM!"
- "All your favourite rock hits, coming up next"
- "It's 3 PM, time for the afternoon show"
- Station promos and special announcements

#### How It Works

1. **Scheduler decision**: When the scheduler selects a song, it checks the current schedule entry's interstitials configuration
2. **Probability roll**: The station's random number generator is used to roll against `interstitials_probability`
3. **Queue building**: If the roll succeeds, a random interstitial is picked from the configured directory and queued after the song
4. **Playback**: The song plays first, then the interstitial plays automatically

#### Notes

- The same directory can be reused across multiple schedule entries
- Each station has its own random number generator, so interstitials on different stations won't synchronise
- The probability is evaluated fresh after each song, so the pattern stays unpredictable

### Top-of-the-Hour Jingles

Set `top_of_the_hour` in your station TOML to a directory containing MP3 files:

```toml
top_of_the_hour = "/path/to/media/toth/MYCALL"
```

The scheduler picks a random file from that directory and plays it as the **first item of every new hour slot**. Once it has played for a given hour, it will not play again until the next hour boundary — even if `_advance_station` is called multiple times within the same hour.

If the directory is missing or empty the feature is silently skipped and normal scheduling continues. No rescan is needed when adding files; just run `scan_media.py` again after populating the directory.

Example media tree:

```
/path/to/media/
└── toth/
    └── MYCALL/
        ├── top-of-hour-1.mp3
        ├── top-of-hour-2.mp3
        └── top-of-hour-3.mp3
```

### Station Idents

Station idents are longer identification announcements that overlay on top of songs. They typically include:
- Call letters: "KXYZ"
- Frequency: "99.9 FM"
- Slogan: "Your home for classic rock"

The music ducks (reduces volume) during ident playback for a professional sound.

### Commercial Breaks

Commercial breaks are automatically triggered based on `break_frequency_s`. When a break is due:
1. Current song finishes
2. Station ident plays
3. Commercials play to fill `break_length_s`
4. Music resumes with an ident overlay

## Database Schema

The system uses SQLite to track:
- **Media**: All songs, idents, commercials, and interstitials
- **Stations**: Station configurations and settings
- **Station Media**: Links between stations and their media
- **Station State**: Current playback state per station
- **Station Interstitials**: Interstitial configurations per schedule entry
- **Plays**: Playback history

## Development

### Project Structure

```
radio-thingy/
├── radio/                  # Main package
│   ├── __init__.py
│   ├── config.py          # RadioConfig dataclass + load_config()
│   ├── db.py              # Database schema and connection
│   ├── helpers.py         # Database query helpers
│   ├── station_config.py  # Station TOML parsing
│   ├── scan_media.py      # Media scanning
│   ├── scheduler.py       # Station scheduler logic
│   ├── player.py          # Audio playback (MPV)
│   ├── input.py           # TuneInput abstraction (GPIO, etc.)
│   ├── api.py             # HTTP API (FastAPI)
│   └── radio.py           # RadioApp — pure library, no entry point
├── stations/              # Station configurations
│   └── station.toml.example
├── play_radio.py          # Entry point (GPIO buttons, loads config.toml)
├── config.toml.example    # Fully documented config template
├── install.sh             # Installation script
├── rescan.py              # Utility to rescan media
└── README.md
```

### Utility Scripts

```bash
# Delete the database and rescan all media
python rescan.py

# Rescan with custom paths
python rescan.py --db ./radio.db --music ~/media/music --stations "./stations/*.toml"

# Scan without nuking the database
python -m radio.scan_media --help
```

## Troubleshooting

### No Audio Output
- Check ALSA/PulseAudio configuration
- Verify MPV can play audio: `mpv test.mp3`
- Check volume levels: `alsamixer`

### Station Not Playing
- Verify schedule is configured for current day/hour
- Check that music exists for configured tags
- Run scanner with `--verbose` to see what's being indexed

### Interstitials Not Playing
- Verify `interstitials_probability` is > 0
- Check that the interstitials directory exists and contains MP3 files
- Rescan media after adding interstitials

### Top-of-the-Hour Jingles Not Playing
- Verify the directory set in `top_of_the_hour` exists and contains MP3 files
- Run `scan_media.py` to index the files and link them to the station

### Performance Issues
- Use a Raspberry Pi 3 or newer
- Close unnecessary background processes
- Consider using a lighter desktop environment

## License

[Your chosen license here]

## Acknowledgments

Built with:
- Python 3
- MPV media player
- SQLite
- Mutagen (audio metadata)

---

**Enjoy your personal FM radio station!** 📻🎵
