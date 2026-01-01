# Radio Thingy 📻

A Python-based FM radio station emulator that brings the nostalgic experience of classic FM radio to your Raspberry Pi. Tune between multiple stations, each with its own frequency, programming schedule, station identifications, interstitials, and commercial breaks.

## Overview

Radio Thingy simulates a complete FM radio ecosystem with multiple stations broadcasting on different frequencies. Each station can have its own 24/7 programming schedule, mixing music with authentic radio station elements like idents (station identifications), interstitials (promos and announcements), and commercial breaks.

Experience the joy of tuning through static between stations, catching your favorite music, and hearing those classic radio elements that made FM radio so engaging.

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
- Customizable frequency and timing
- Audio ducking - music volume reduces during ident playback
- Configurable fade in/out for smooth transitions

### 🎬 Interstitials (NEW!)
- Play short promotional clips between songs
- Configure per hour and per music tag
- Adjustable probability (0.0 to 1.0) for how often they play
- Perfect for "Now playing your favorite rock hits!" style announcements

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
- Per-station seeded randomization for variety
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

### Future Hardware Support
🚧 **Coming Soon**: Physical control interface support
- Rotary encoder for tuning between stations
- Physical buttons for preset stations
- Volume knob
- Optional display for frequency/station information

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

### Directory Structure

Organize your media files as follows:

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
ident_pad_s = 2.0          # Start 2 seconds into song
ident_duck = 0.4           # Reduce music to 40% during ident
ident_ramp_s = 0.5         # 0.5 second fade

[schedule.monday]
7 = { tags = "pop", interstitials = "/path/to/interstitials/morning", interstitials_probability = 0.5 }
8 = { tags = "pop", interstitials = "/path/to/interstitials/morning", interstitials_probability = 0.5 }
# ... more hours ...
```

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

You can rescan anytime you add new media files.

## Usage

### Starting the Radio

```bash
python -m radio.radio --db /path/to/radio.db
```

The radio will start playing with:
- Initial station tuned to the first configured station
- Appropriate programming based on current time
- Background tick updating all stations

### Interacting with the Radio (via code)

Currently, interaction is programmatic. The `RadioApp` class provides:

```python
# Tune to a frequency
radio.tune_to(99.9)

# Get current status
status = radio.get_status()
print(f"Station: {status['station']}")
print(f"Frequency: {status['freq']}")
print(f"Now Playing: {status['kind']}")
```

🚧 **Physical controls coming soon!**

## Key Concepts

### Tags and Music Selection

Music files are organized by tags (genres/categories). The tag is determined by the parent directory name:

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

Interstitials are short audio clips (typically 5-30 seconds) that play between songs. They're perfect for:
- "You're listening to MYCALL, 99.9 FM!"
- "All your favorite rock hits, coming up next"
- "It's 3 PM, time for the afternoon show"
- Station promos and special announcements

Configure probability per hour:
- `0.0` = never play
- `0.3` = 30% chance after each song
- `1.0` = play after every song

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
4. Music resumes with ident overlay

## Database Schema

The system uses SQLite to track:
- **Media**: All songs, idents, commercials, and interstitials
- **Stations**: Station configurations and settings
- **Station Media**: Links between stations and their media
- **Station State**: Current playback state per station
- **Station Interstitials**: Interstitial configurations per schedule
- **Plays**: Playback history

## Development

### Project Structure

```
radio-thingy/
├── radio/                  # Main package
│   ├── __init__.py
│   ├── db.py              # Database schema and connection
│   ├── helpers.py         # Database query helpers
│   ├── station_config.py  # Configuration parsing
│   ├── scan_media.py      # Media scanning
│   ├── scheduler.py       # Station scheduler logic
│   ├── player.py          # Audio playback (MPV)
│   └── radio.py           # Main radio application
├── stations/              # Station configurations
│   └── station.toml.example
├── install.sh            # Installation script
├── rescan.py             # Utility to rescan media
└── README.md
```

### Running Tests

```bash
# Rescan all media
python rescan.py

# Scan with custom paths
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
- Check that interstitial directory exists and contains MP3s
- Rescan media after adding interstitials

### Performance Issues
- Use a Raspberry Pi 3 or newer
- Close unnecessary background processes
- Consider using a lighter desktop environment

## Future Enhancements

- 🎛️ Physical control interface (rotary encoder, buttons)
- 📟 Optional display showing station info
- 🌐 Web interface for remote control
- 📱 Mobile app for tuning
- 🎨 Visual spectrum analyzer
- 📊 Playback statistics and reports
- 🔊 Multi-room audio support
- ☁️ Cloud music library integration

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

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

