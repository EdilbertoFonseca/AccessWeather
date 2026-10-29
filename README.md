# AccessWeather

An add-on for the [NVDA](<https://www.nvaccess.org/>) screen reader that announces current weather conditions and forecasts using the [Open-Meteo](<https://open-meteo.com/>) API, with no API key required.

## Installation

- Through the NVDA **Add-on Store** (Tools → Add-on Store), or
- By downloading the `.nvda-addon` file from the [Releases](<https://github.com/tadeujrtec/AccessWeather/releases>) tab and opening it.

## Usage

Single shortcut: `NVDA + Shift + W`, pressed one or more times:

| Presses | Action |
| --- | --- |
| 1x | Announces the current weather for the default location |
| 2x | Lists the next 24 hours |
| 3x | Lists the upcoming days |
| 4x | Opens the AccessWeather settings in NVDA |
| 5x | Enables/disables custom location announcements |

The multi-press timeout is the same as the one configured in NVDA. Only the action corresponding to the final number of presses is triggered.

## Features

- Saved locations, including a default location, reordering, and name-based search.
- Customizable announcement fields that can be reordered for each location (`Alt+Arrow keys`); `F2` reads the value of the selected field for the chosen location.
- Automatic announcements for each location at configurable intervals (1 to 360 minutes).
- Location-specific beep sequences and global beeps before the single-press announcement.
- Offline cache and Portuguese-language formatting.
- Wind speed and direction (8-point compass rose).
- Wind gusts, cloud cover, visibility, and atmospheric pressure.
- UV index with classification and air quality (AQI and PM2.5).
- Continuous rain, showers, and hours of rainfall during the day.
- Sunrise and sunset, moonrise and moonset, and moon phase included in announcements.
- Sunshine hours, day length, and maximum and minimum feels-like temperatures.
- Configurable units (metric/imperial), wind units, and time and date formats.
- A What's New window displayed once per version, with an option to disable it and a button to read it again.

## Data

The add-on stores all data in `%APPDATA%\nvda\accessWeather\` (`settings.json`, `locations.json`, and `cache.json`).

## Structure

text

```
addon/accessWeather/
├── manifest.ini
└── globalPlugins/accessWeather/
    ├── __init__.py
    ├── dialogs.py
    ├── playback.py
    └── core/
```

## License

[GPL v2 or later](<https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>).
