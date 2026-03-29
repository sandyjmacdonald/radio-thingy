# 💀 deadair 💀

deadair is a Python-based FM radio station emulator that brings the nostalgic experience of classic FM radio to your Raspberry Pi. Tune between multiple stations, each with its own frequency, programming schedule, station identifications, overlays, and commercial breaks. It even mixes in white noise when tuning between stations for that authentic old radio feel. Use it to bring a beautiful, old radio back to life, in the way that you remember.

deadair encourages you to own your music — pay your favourite artists for their music and then listen by your rules. Collect together all your favourite songs and then have them play back randomly, no skipping songs, just let fate decide what comes on next. Turn on and tune in.

## Features

### 🎵 Multiple Stations
- Configure multiple stations, each with unique names or call signs and FM frequencies
- Realistic static/noise when tuning between stations
- Independent programming and schedules per station
- Also supports internet radio station streams

### 📅 Flexible Scheduling
- 24/7 programming schedules with hourly granularity
- Different schedules for each day of the week
- Mix multiple music genres within a single hour
- Tag-based music selection from your library

### 🎙️ Station Idents (Jingles)
- Station idents play between songs as standalone clips
- Configurable frequency (how often they appear)
- Perfect for call signs, frequency stabs, and short station branding clips

### 🎬 Overlays
- Short audio clips that play over the top of a song with audio ducking
- Configure per schedule entry — different overlays for different hours/days
- Adjustable probability (0.0 to 1.0) for how likely they are to play over each song
- Configurable fade in/out and pad time for smooth transitions
- Perfect for "You're listening to WABC 99.9 FM!" style announcements, dedications, or weather and traffic news

### ⏰ Top-of-the-Hour Idents
- Clips that play specifically at the top of each hour, as the first item that plays
- This is ideal for the standard "WABC, New York", a legal requirement on US radio stations

### 📢 Commercial Breaks
- Scheduled commercial breaks at configurable intervals
- Automatic break construction (ident + commercials)
- Target length with intelligent media selection
- Automatic return to music after breaks

### 🎚️ Audio Features
- Seamless continuity when switching stations
- MPV-based playback for reliable audio
- Support for external DACs and amplifiers

### 🔘 GPIO Button Inputs
- Optional push-buttons on any GPIO pins for station cycling and mute control
- **Station cycle**: steps through all configured stations in frequency order, wrapping back to the first after the last
- **Mute/unmute**: sets volume to 0; on unmute restores the current potentiometer position (if one is configured) or the last known volume
- Configured in `config.toml` via a `[buttons]` table — keys are BCM GPIO pin numbers, values are the RadioApp method to call on press

### 💡 Tuning LED
- Optional PWM LED on any GPIO pin that gives physical feedback as you tune
- Fades from off at the edge of the tuning window up to full brightness when locked to a station
- Brightness tracks the same gain curve used for audio, so the LED and sound fade in together
- Configured in `config.toml` via `tuning_led_pin` and `led_brightness`

### 📴 Off-Air Programming
- Configure a looping MP3 that plays whenever a station has no schedule entry for the current hour
- Set per-station in the station TOML — each station can have its own off-air audio
- Falls back to static noise if no off-air file is configured

### 🔧 Smart Scheduler
- Intelligent song selection based on duration to fit time slots
- Avoids playing the same song on multiple stations simultaneously, or the same song too frequently
- Per-station seeded randomisation for variety
- Queue system for seamless playback of breaks and idents

## Recommended Hardware

- **Raspberry Pi 4 or 5**
- **External DAC/Amplifier**
  - HiFiBerry DAC+ or similar
  - USB DAC
  - I2S DAC HAT
- **Quality speakers or headphones**

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/sandyjmacdonald/deadair deadair
cd deadair
```

### 2. Run the Installation Script

```bash
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

## Making / Finding Station Idents, etc.

For me, a lot of the fun with this project has been making up fictitious ads, station idents, little bits of DJ chatter, and so on. I've used ElevenLabs Text to Speech, Sound Effects, and Music to do this, but you may want to use another tool to do that, or even be your own DJ and use your own voice (I have a very boring Scottish voice).

You might also want to pull out bits from real vintage radio broadcasts, from somewhere like the Internet Archive, although be aware of any restrictions around copyright and IP that may apply.

## Configuration

### Runtime Configuration (`config.toml`)

All runtime settings live in a single TOML file. Copy the provided example and edit the paths:

```bash
cp config.toml.example config.toml
```

The first three keys are **required**; everything else has a sensible default:

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
| `tuning_led_pin` | | `null` | BCM GPIO pin number for the tuning LED (omit to disable) |
| `led_brightness` | | `0.5` | Maximum PWM brightness for the tuning LED, 0.0–1.0 |
| `button_debounce` | | `0.05` | Button debounce window in seconds |
| `buttons` | | `[]` | Array of `{ pin, action }` entries mapping GPIO pins to button actions (see below) |
| `tick_s` | | `0.25` | Main loop tick interval in seconds |
| `api_host` | | `"0.0.0.0"` | HTTP API bind address |
| `api_port` | | `8000` | HTTP API port |

See `config.toml.example` for a full example with inline comments.

### Suggested Directory Structure

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
├── idents/                   # Station identifications (play between songs)
│   ├── MYCALL/
│   │   ├── ident1.mp3
│   │   └── ident2.mp3
│   └── OTHERCALL/
│       └── ident.mp3
├── commercials/              # Commercial/advertisement files
│   ├── MYCALL/
│   │   ├── ad1.mp3
│   │   └── ad2.mp3
│   └── OTHERCALL/
│       └── generic-ad.mp3
├── toth/                     # Top-of-the-hour jingles
│   ├── MYCALL/
│   │   ├── toth1.mp3
│   │   └── toth2.mp3
│   └── OTHERCALL/
│       └── toth.mp3
└── overlays/                 # Voice-over clips that play over songs
    ├── MYCALL/
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

Edit the file to configure your station, for example:

```toml
name = "MYCALL"
freq = 99.9

idents_dir = "/path/to/media/idents/MYCALL"
commercials_dir = "/path/to/media/commercials/MYCALL"
top_of_the_hour = "/path/to/media/toth/MYCALL"
off_air_file = "/path/to/media/off_air/MYCALL.mp3"

break_frequency_s = 900    # Commercial break every 15 minutes
break_length_s = 60        # 60-second breaks

ident_frequency_s = 180    # Station ident between songs every 3 minutes

overlay_pad_s = 2.0        # Start overlay 2 seconds into the song
overlay_duck = 0.4         # Reduce music to 40% during overlay
overlay_ramp_s = 0.5       # 0.5 second fade

[schedule.monday]
# Morning drive - frequent overlays
7 = { tags = "pop", overlays = "/path/to/overlays/morning", overlays_probability = 0.5 }
8 = { tags = "pop", overlays = "/path/to/overlays/morning", overlays_probability = 0.5 }
.
.
.
# Midday - occasional overlays
12 = { tags = "pop", overlays = "/path/to/overlays/midday", overlays_probability = 0.2 }
.
.
.
# Evening - different content, always overlay
18 = { tags = "rock", overlays = "/path/to/overlays/evening", overlays_probability = 1.0 }
.
.
.
# Late night - no overlays
23 = { tags = "pop" }
```

See `stations/station.toml.example` for a complete example with detailed comments.

### Scanning Media

After configuring your station(s), scan your media library:

```bash
python rescan.py
```

This will:

- Index all MP3 files in your music library
- Scan station idents and commercials
- Scan overlays from schedule configurations
- Build the database for playback

You can rescan any time you add new media files.

## Usage

### Playing the Radio

```bash
python play_radio.py --config /path/to/config.toml
```

`play_radio.py` is the sole entry point. It reads `CONFIG_PATH` (either passed in, as above, or set in the `play_radio.py` script`), then wires up any inputs (e.g. GPIO buttons, potentiometers, encoders), and starts the radio playing.

The radio will start playing with:

- The first configured station, or last station tuned to
- Appropriate programming based on current time
- Background tick updating all stations

To run without inputs (e.g. for API-only use), you can instantiate `RadioApp` directly with no inputs:

```python
from radio.config import load_config
from radio.radio import RadioApp

app = RadioApp(config=load_config("/path/to/config.toml"), inputs=[])
app.run()
```

### Tuning LED

To add a tuning LED, connect a PWM-capable LED (with an appropriate resistor) to any BCM GPIO pin and set `tuning_led_pin` in `config.toml`:

```toml
tuning_led_pin = 17     # BCM pin number
led_brightness = 0.8    # optional, default 0.5
```

`play_radio.py` will pick this up automatically — no code changes needed. If you want to wire it up manually:

```python
from radio.config import load_config
from radio.input import TuningLED
from radio.radio import RadioApp

cfg = load_config("/path/to/config.toml")
tuning_led = TuningLED(cfg.tuning_led_pin, max_brightness=cfg.led_brightness)
app = RadioApp(config=cfg, inputs=[...], tuning_led=tuning_led)
app.run()
```

The LED uses `gpiozero.PWMLED` under the hood, so any `gpiozero`-supported pin will work.

### GPIO Buttons

Add a `[buttons]` table to `config.toml`. Keys are BCM GPIO pin numbers; values are the `RadioApp` method to call when the button is pressed:

```toml
buttons = [
    { pin = 23, action = "tune_next_station" },   # cycle to the next station
    { pin = 24, action = "toggle_mute" },          # mute / unmute
]
```

Available actions:

| Action | Description |
|---|---|
| `tune_next_station` | Steps to the next station in frequency order, wrapping back to the first after the last |
| `toggle_mute` | Sets volume to 0; on unmute restores the current potentiometer position (if active) or the last known volume |

`RadioApp` picks this up automatically from config — no code changes needed. Buttons use `gpiozero.Button` with internal pull-up resistors.

### Running as a systemd service

To have deadair start automatically on boot, run the provided setup script as the radio user (no `sudo` needed):

```bash
bash setup_service.sh
```

This creates a systemd **user** service (`~/.config/systemd/user/deadair.service`) that:

- Starts `play_radio.py` from the project directory using the virtualenv Python
- Restarts automatically on failure (5-second delay)
- Waits for PipeWire/PulseAudio to be available before starting
- Enables linger so the service starts at boot without requiring a login session

After setup, the service is enabled and started immediately. Useful commands:

```bash
systemctl --user status deadair     # check status
systemctl --user stop deadair       # stop
systemctl --user restart deadair    # restart
journalctl --user -u deadair -f     # follow logs
```

> **Note:** `install.sh` must have been run first — `setup_service.sh` will exit with an error if the virtualenv is not found.

## Web API

When the radio starts, a FastAPI server starts automatically on port `8000`. All endpoints are read-only except `/tune`.

### `GET /stations`

Returns all configured stations sorted by frequency.

```bash
curl http://localhost:8000/stations
```

```json
[
  { "name": "KABC", "frequency": 92.5, "station_type": "regular" },
  { "name": "WXYZ", "frequency": 95.1, "station_type": "stream" }
]
```

---

### `GET /status`

Returns the current state of the dial — what is playing right now.

```bash
curl http://localhost:8000/status
```

```json
{
  "frequency": 92.5,
  "station": "KABC",
  "station_type": "regular",
  "tuned": true,
  "now_playing": {
    "type": "song",
    "artist": "KiSS",
    "title": "I Was Made for Lovin' You",
    "started_at": "2026-03-06T20:35:28.995+00:00",
    "ends_at": "2026-03-06T20:39:29.248+00:00",
    "duration_s": 240.25,
    "elapsed_s": 60.05
  }
}
```

| Field | Description |
|---|---|
| `frequency` | Current dial frequency in MHz |
| `station` | Name of the nearest station |
| `station_type` | `"regular"` or `"stream"` |
| `tuned` | `true` when the dial is close enough to a station to hear it |
| `now_playing` | `null` when not tuned; `{"type": "noise"}` when tuned to static; full object when playing |
| `type` | One of: `song`, `overlay`, `ident`, `commercial`, `top_of_hour`, `off_air`, `noise` |
| `elapsed_s` | Seconds since the current track started, computed at request time |

**Optional `?station=` parameter**

Pass a station name to query any station regardless of what is currently tuned:

```bash
curl "http://localhost:8000/status?station=WXYZ"
```

This always returns `now_playing` for the named station. `tuned` reflects whether the dial is actually on that station. Returns `404` for unknown station names.

---

### `POST /tune`

Moves the dial to a station by name or to a specific frequency. Returns the updated `/status` response.

**Tune to a station by name:**

```bash
curl -X POST "http://localhost:8000/tune?station=KABC"
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

### Day Templates

If several days share the same schedule, define it once as a named template and reference it by name instead of repeating it:

```toml
[day_templates.weekday]
0  = { tags = "ambient" }
6  = { tags = "pop", overlays = "/path/to/overlays/morning", overlays_probability = 0.5 }
12 = { tags = ["pop", "dance"] }
17 = { tags = "rock" }
22 = { tags = "chill" }

[day_templates.weekend]
0  = { tags = "dance" }
10 = { tags = ["pop", "indie"] }
20 = { tags = "dance", overlays = "/path/to/overlays/party", overlays_probability = 1.0 }

[schedule]
monday    = "weekday"
tuesday   = "weekday"
wednesday = "weekday"
thursday  = "weekday"
saturday  = "weekend"
sunday    = "weekend"

[schedule.friday]
# Friday is unique — defined as a normal subtable, not a template
17 = { tags = ["pop", "dance"], overlays = "/path/to/overlays/weekend", overlays_probability = 0.6 }
```

Days assigned to a template and days defined as subtables can be freely mixed. Any day whose name is not mentioned is treated as having no programming (off-air or noise).

### Off-Air Programming

When a station has no schedule entry for the current hour — whether because the day is unscheduled, or because no entry covers that hour — it can loop a dedicated off-air MP3 instead of falling back to static noise.

Set `off_air_file` in the station TOML to the path of an MP3 to loop:

```toml
off_air_file = "/path/to/media/off_air/MYCALL.mp3"
```

The file loops continuously for the duration of the unscheduled hour. At the top of the next hour the scheduler re-evaluates: if programming resumes, playback switches to normal songs; if the hour is still unscheduled, the off-air file restarts.

If `off_air_file` is not set, the station falls back to the global static noise file (the existing default behaviour).

### Station Idents

Idents are short station identification clips that play **between songs** as standalone items. They're triggered by `ident_frequency_s` — when enough time has passed since the last ident, one is queued to play after the current song finishes. They're perfect for:

- Call-letter stings: "KABC"
- Frequency tags: "92.5 FM"
- Short branding jingles

During commercial breaks, an ident plays as the first item of the break (before the commercials).

### Overlays

Overlays are audio clips that play **over the top of a song** while it continues underneath at reduced volume (ducked). They're configured per schedule entry and triggered by a probability roll when each song starts. They're perfect for:

- "You're listening to KABC, 92.5 FM!"
- "All your favourite rock hits, coming up next"
- "It's 3 PM, time for the afternoon show"
- Station promos and special announcements

#### How Overlays Work

1. **Scheduler decision**: When a song starts, the scheduler checks the current schedule entry's overlay configuration
2. **Probability roll**: The station's random number generator rolls against `overlays_probability`
3. **Scheduled**: If the roll succeeds, a random overlay is picked from the configured directory and scheduled to fire `overlay_pad_s` seconds into the song
4. **Ducking**: When the overlay fires, music fades down to `overlay_duck` volume over `overlay_ramp_s` seconds, the overlay plays, then music fades back up

Notes:

- The same directory can be reused across multiple schedule entries
- Each station has its own random number generator, so overlays on different stations won't synchronise
- The probability is evaluated fresh when each song starts, so the pattern stays unpredictable
- After a commercial break, an overlay is forced on the next song

### Commercial Breaks

Commercial breaks are automatically triggered based on `break_frequency_s`. When a break is due:
1. Current song finishes
2. Station ident plays
3. Commercials play to fill `break_length_s`
4. Music resumes with an overlay forced on the next song

## Database Schema

The system uses SQLite to track:
- **Media**: All songs, idents, overlays, commercials, and top-of-hour jingles
- **Stations**: Station configurations and settings
- **Station Media**: Links between stations and their media
- **Station State**: Current playback state per station
- **Station Overlays**: Overlay configurations per schedule entry
- **Plays**: Playback history