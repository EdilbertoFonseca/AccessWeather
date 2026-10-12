# AccessWeather - Instructions for Agents

## Project Scope

AccessWeather is a portable Windows desktop weather application written in
Python and wxPython. It shows hourly and daily forecasts, a list of saved
locations with the important values on each row, and Windows toast
notifications driven by per-location alerts. The UI is
accessibility-oriented (NVDA/SAPI announcements) and the whole window is
navigable by keyboard.

Weather data comes from **Open-Meteo** (`api.open-meteo.com` and
`geocoding-api.open-meteo.com`): free, no API key, no account, no secrets in
the repository.

The project root is the directory containing this file:

```text
C:\Junior\Apps\Meus Programas\AccessWeather
```

The same tree should also be reachable through a junction under
`C:\Junior\PortableApps\Meus Programas\AccessWeather`.

## Status

The feature set for `0.1.0` is complete: portable settings, announcements, tray
icon, changelog, the updater, the Open-Meteo client (`app/weather.py`), the
saved-locations store (`app/locations.py`), the forecast cache
(`app/cache.py`), the row/text helpers (`app/formatting.py`), alert rules
(`app/alerts.py`), Windows toasts (`app/notify.py`), the dialogs
(`app/dialogs.py`) and the main window in `application.py`. Everything still
needs manual screen-reader testing with `main.py` before a release.

## Source Layout

- `main.py`: development entry point (DPI awareness, then `run()`).
- `app/config.py`: `APP_NAME`, `APP_AUMID`, action/announcement/notification
  labels, `DEFAULTS`, unit groups, `Settings` persistence and portable paths
  (`app_root`, `data_dir`, `tools_dir`).
- `app/application.py`: `Controller` frame: location/current/hourly/daily
  views, menus, context menu, keyboard handling, refresh timer, worker threads,
  `dispatch`, tray lifetime, announcements.
- `app/weather.py`: Open-Meteo geocoding and forecast; `Place`, `Forecast`,
  `HourlyPoint`, `DailyPoint`, `CurrentWeather`, the WMO label/severity tables
  and `WeatherError`.
- `app/locations.py`: `SavedLocation` and `LocationStore`; saved locations,
  order, default location, alias, favourites and per-location alert rules.
- `app/cache.py`: `ForecastCache` over `data/cache.json`; stores raw payloads
  with timestamps, freshness checks, prune and atomic save.
- `app/formatting.py`: pure row/text builders for the lists, current
  conditions and announcements; no wx and no network.
- `app/alerts.py`: alert rule model (`AlertRule`), the metric table, the
  Portuguese descriptions and evaluation against a `Forecast`.
- `app/notify.py`: `Notifier`; Windows toasts through `windows_toasts` (optional
  import), gated by the `notifications` settings group.
- `app/dialogs.py`: settings, the alert-rule editor, the alerts list, the
  per-location weather-notification editor and the text report/about dialogs.
- `app/tray.py`: system-tray menu.
- `app/announce.py`: NVDA DLL or SAPI speech.
- `app/updater.py`: update check/download/apply flow.
- `app/changelog.py`: remote changelog with a bundled fallback.
- `app/version.py`: `VERSION`, `APP_NAME`, `UPDATE_URL`, `CHANGELOG_URL`.
- `tests/`: offline `unittest` suite.
- `tools/`: runtime assets shipped with releases (toast icon); not source code.
- `data/`: runtime data, not source code.
- `build.ps1`: PyInstaller one-file build (`--onefile --windowed`).

## Runtime Data and Secrets

`data/` holds the user's data and must never ship inside a public build or the
update zip:

- `settings.json`: preferences.
- `locations.json`: saved locations and alert rules.
- `cache.json`: last forecast payloads and their timestamps.
- `update-installed.json`: marker written by the updater after installing.

Open-Meteo needs no key, so there are no credentials to protect. Still, never
expose `data/` or `cache/` contents in a public download, an update zip or a
bug report.

## Updates and Releases

Same flow as AccessPlayer: the updater compares the local `VERSION` against a
strict-JSON `version.json` on a public web root.

- `https://jrtec.ddns.net/updates/accessweather/version.json`
- `https://jrtec.ddns.net/updates/accessweather/changelog.md`

`version.json` must be strict valid JSON. Changelog line breaks inside the
string must be escaped as `\n`; never insert raw line breaks inside a JSON
string. Test the public update URL before release (`requests.Response.json()`).

The update zip must contain only `AccessWeather.exe` and the `tools/` folder.
It must not include `data/`, source code or private deployment keys.
`data_dir()` sits next to the executable, so existing user data survives
extraction.

Keep `app/version.py`, `CHANGELOG.md` and the remote `version.json` consistent.
`app/changelog.py` also carries `FALLBACK_CHANGELOG` for offline use; update it
together with `CHANGELOG.md`.

After each version is published and the public download has been verified,
move `dist/AccessWeather.exe` to `AccessWeather.exe` in the project root. Check
any existing root executable before replacing it. Once the executable is
securely in the root, delete the local `build/` and `dist/` directories and the
generated `AccessWeather.spec`. Keep the root executable for local use.

## Weather Data

- Open-Meteo only. Do not add a second provider in v1 and do not require an API
  key.
- Unit codes come from `UNIT_GROUPS` in `app/config.py`; the user choice is
  stored in `units` and the optional `units_wind` override. Never hardcode
  Celsius or km/h in the UI.
- WMO weather codes must be mapped to Portuguese labels in one place so the
  lists, the announcements and the toasts never disagree. That place is
  `WMO_LABELS`/`describe_code` in `app/weather.py`. Weather conditions are
  decided by `code_severity` and `is_precipitation`, never by ad-hoc
  comparisons elsewhere.
- Cache successful payloads in `data/cache.json` with a timestamp so the window
  can open instantly and offline; `cache_minutes` controls reuse.
- Respect the Open-Meteo terms: keep the request rate low, reuse the cache and
  set an identifying `User-Agent`.

### weather.py contract

- `search_places(query, count)` returns a tuple of `Place` and never raises for
  an empty query or an empty result; it only raises `WeatherError` when the
  service fails. Invalid entries in a response are skipped, not fatal.
- `fetch_forecast(place, settings)` reads `units`, `daily_days` and
  `hourly_hours` from `settings`, builds the request with
  `build_forecast_params` and parses it with `parse_forecast`. Do not build the
  Open-Meteo URL by hand anywhere else.
- `request_json` sets the `User-Agent`, retries temporary responses (`429`,
  `500`, `502`, `503`, `504`) and connection errors up to three attempts, and
  raises `WeatherError` with a Portuguese message on failure. Every network
  call must go through it.
- `parse_forecast` is pure and never touches the network; every parsing detail
  is covered by `tests/test_weather.py`. Keep it tolerant of missing values and
  ragged series — the API occasionally returns `null` inside a series.
- Datetimes are naive local times from Open-Meteo (`timezone=auto`); never
  re-localize them with `datetime.now()`.
- `Forecast.hourly_in_window(start)`, `next_days(count)` and `worst_severity()`
  are the intended helpers for the UI; do not re-implement the slicing inline.

## Saved Locations

- `LocationStore` owns `data/locations.json`; nothing else may read or write
  that file directly. Always call `save()` after a mutation that must persist.
- A location is identified by `SavedLocation.key` (which comes from
  `Place.key`). When adding, dedupe by `place_id` first and fall back to the
  coordinate key, so re-adding a searched place refreshes its data instead of
  duplicating it.
- The list order is the display order; use `move`, `move_to` and `reorder` and
  keep the default location (`default_key`) pointing at an existing entry.
- `alias` is the user's name for the place; `display_name`/`full_label` are the
  only ways the UI should render it. Never blank out the real place name.
- `alerts` holds opaque alert rules produced and interpreted by `alerts.py`.
  This store only persists them; do not give them meaning here.
- `notify_hourly`/`notify_fields`/`notify_interval` hold the per-location
  notification choice; validate field keys against `WEATHER_NOTIFICATION_FIELDS`
  and clamp the interval with `clamp_notification_interval` when loading or
  saving (use `set_notification`).
- Loading must stay tolerant: a corrupted file, an invalid entry, a duplicate
  key or a stale default is repaired or skipped, never fatal.
- Destructive actions (removing a location, clearing the list) need a
  confirmation in the UI before the store method is called.

## Notifications

- Use Windows toasts through `windows_toasts`; it must stay an optional import
  so the app still runs without it. Prefer `WindowsToaster` (works for a
  portable, non-installed app); the `InteractableWindowsToaster` fallback with
  the custom AUMID only displays once that AUMID is registered with Windows, so
  it is a fallback, not the primary backend.
- `APP_AUMID` in `app/config.py` must stay stable across releases; changing it
  makes Windows treat the update as a different app.
- Alert toasts, forecast summaries and update notices are individually toggled
  through the `notifications` settings group.
- Each saved location can also opt into a periodic weather notification, with
  its own ordered field selection and interval. It is controlled by
  `notify_hourly` (on/off), `notify_fields` (ordered field keys) and
  `notify_interval` (minutes, 1 to 360, default 60). It is enabled and
  previewed from the location context menu ("Personalizar notificação de
  clima..."). The dialog lists every field in a checkable list: the check marks
  what appears and the list order is the toast order, changed with
  `Alt+Up`/`Alt+Down` or the move buttons. A combobox picks the interval, which
  is clamped with `clamp_notification_interval` (an editable combo, so any
  value in range can be typed). Its "Testar notificação" button forces a real
  toast (ignoring the notification toggles) and only falls back to a message
  box, with the reason, when the toast cannot be shown. Field keys come from
  `WEATHER_NOTIFICATION_FIELDS`; the default is `DEFAULT_NOTIFICATION_FIELDS`.
  `formatting.notification_body` renders it.

## Threading and UI Rules

- Use worker threads for network work (forecast fetch, geocoding, update
  check); never touch wx controls from those threads.
- Update wx controls only on the UI thread, normally through `wx.CallAfter`.
- `Controller` uses sequence counters and `_closing` to discard stale
  asynchronous results; check them before applying results.
- `_announce_status(message, category)` respects the announcements settings;
  categories come from `ANNOUNCEMENT_LABELS` in `app/config.py`.
- Every action listed in `ACTION_LABELS` needs a handler reachable from the
  tray menu; unknown actions must announce instead of raising.

## Keyboard and Accessibility Rules

- UI is built from wx lists, notebooks and plain controls, in this order:
  readable names, keyboard reachability, then visuals.
- Preserve Portuguese labels and descriptive text used by the existing UI.
- Context menus must also work with the Applications key and `Shift+F10`;
  right-click selects the item under the pointer before opening the menu.
- Do not use tooltips on wx menu items.
- Modal dialogs should close with `EndModal`, not `Close()`, when the caller
  uses `ShowModal()`.
- Lists must report the essential values in the row text itself, because a
  screen reader reads the cell, not a hover state.
- Do not rely on colour alone to signal an alert; state it in words.
- Windows opened from the tray are shown through `Controller._present`, so
  they are activated instead of only being shown.

## Validation

Run from the project root:

```powershell
python -m compileall -q app tests
python -m unittest discover -s tests -p "test_*.py"
```

The suite must stay offline: network access is mocked. Verify GUI behavior and
screen-reader interaction manually by running `main.py`.

Before building a release:

1. Compile/import the changed modules and run the full test suite.
2. Test the location list, the hourly and daily lists, the settings and the
   alert dialogs with a screen reader.
3. Confirm the frozen executable fetches a forecast, shows a toast and restores
   the saved locations.
4. Verify the public `version.json` parses as strict JSON and the update flow
   checks, downloads and relaunches correctly.

## Editing and Collaboration

- Make the smallest correct change and preserve working features.
- Conserve the user's shared GPT/OpenAI API budget: keep progress and final
  responses concise, avoid redundant reads/searches, batch independent tool
  calls, and run only validations relevant to the change. Do not compromise
  correctness or skip a validation explicitly requested by the user.
- Never use destructive Git or filesystem commands to discard user changes.
- Inspect the worktree before editing; unrelated existing changes may belong
  to the user.
- Do not commit, push or deploy unless explicitly requested.
- Keep comments short and explain only non-obvious behavior.