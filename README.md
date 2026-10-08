# Economic Calendar

A free, open-source panel that shows the day's and the week's **High / Medium / Low impact** economic news in one clean window. Data comes from the ForexFactory weekly feed. Runs on **Windows, macOS and Linux**.

No account, no ads, no tracking.

## Features

- **Today** and **Full Week** views, with the next releases highlighted as they approach
- Filter by impact (High / Medium / Low) and by currency
- Timezone picker (UTC−12 … UTC+14) that is remembered between runs
- Notes panel with auto-save and bold / italic (`Ctrl+B` / `Ctrl+I`); drag the divider to resize it
- Light and dark themes, both tuned for comfortable reading
- Optional always-on-top pin
- Works offline from a local cache when the feed can't be reached
- Announcement box next to the tabs for news about new versions

## Download

Get the latest file for your system from the [Releases](https://github.com/zekibilenay/economic-calendar/releases) page:

| System | File | How to start |
|---|---|---|
| Windows | `EconomicCalendar-windows.zip` | Extract, run `EconomicCalendar.exe` |
| macOS (Apple Silicon: M1 and newer) | `EconomicCalendar-macos-arm64.zip` | Extract, open `EconomicCalendar.app` |
| macOS (Intel) | `EconomicCalendar-macos-intel.zip` | Extract, open `EconomicCalendar.app` |
| Linux (64-bit) | `EconomicCalendar-linux.tar.gz` | `tar -xzf EconomicCalendar-linux.tar.gz`, then run `EconomicCalendar/EconomicCalendar` |

### Windows: SmartScreen warning

The app is not code-signed, so Windows may show an "unknown publisher" warning. Choose **More info → Run anyway**.

### macOS: "cannot be opened" warning

The app is not signed with an Apple developer certificate, so Gatekeeper blocks it the first time. Either right-click `EconomicCalendar.app` and choose **Open → Open**, or remove the download flag once in Terminal:

```
xattr -dr com.apple.quarantine EconomicCalendar.app
```

### Linux

If the file manager doesn't start it, run `chmod +x EconomicCalendar/EconomicCalendar` first.

### Verify your download

You don't have to trust the files blindly:

1. **Open source:** [`economic_calendar.py`](economic_calendar.py) is a single readable file.
2. **Built by GitHub Actions:** every file is built from this repository by [`.github/workflows/build.yml`](.github/workflows/build.yml). To verify:
   `gh attestation verify <downloaded file> --repo zekibilenay/economic-calendar`
3. **Checksum:** each file has a `.sha256` file next to it on the release page. Compare it with `Get-FileHash <file>` (PowerShell) or `shasum -a 256 <file>` (macOS / Linux).
4. **No download at all:** run it from source (below).

## Privacy

- Your notes and settings stay on your computer, in your user folder (`.econ_cal_notes.txt`, `.econ_cal_settings.json`, `.econ_cal_cache_this.json`).
- Network connections:
  1. Calendar data from `nfs.faireconomy.media` (the ForexFactory feed).
  2. One HTTPS GET for the announcement file. No identifiers or personal data are sent; the server only sees `User-Agent: EconomicCalendar/<version>`.

## Run from source

Requires Python 3.9+ with tkinter. No extra packages are needed.

```
python economic_calendar.py
```

- **Windows:** tkinter ships with the Python installer. `Economic_Calendar.vbs` starts the app without a console window.
- **macOS:** use the Python from python.org (it includes tkinter).
- **Linux:** install tkinter first, e.g. `sudo apt install python3-tk` (Debian / Ubuntu) or `sudo dnf install python3-tkinter` (Fedora).

To build it yourself:

```
pip install pyinstaller
pyinstaller --onedir --windowed --name EconomicCalendar --icon economic_calendar.ico --add-data "economic_calendar.ico;." --add-data "economic_calendar.png;." economic_calendar.py
```

On macOS / Linux use `:` instead of `;` in `--add-data`, and `economic_calendar.icns` for `--icon` on macOS.

## Announcements

The app reads the shared announcement feed from [zekibilenay/announcements](https://github.com/zekibilenay/announcements). When there is more than one announcement they rotate every 10 seconds. The feed address is `ANNOUNCE_URL` in `economic_calendar.py` (HTTPS only; it can be overridden with the `ECONCAL_ANNOUNCE_URL` environment variable).

## Releasing a new version

1. Update `APP_VERSION` in `economic_calendar.py`.
2. Add a section to **What's new** below.
3. Tag and push:
   ```
   git tag v1.1.1
   git push --tags
   ```

GitHub Actions builds the Windows, macOS (Apple Silicon and Intel) and Linux files and attaches them to one release.

## What's new

Newest first. Every update gets its own section here.

### v1.1.0

- The announcement box moved up next to the **Today / Full Week** tabs, so it no longer takes a row of its own
- New downloads for **macOS** (Apple Silicon and Intel) and **Linux**, built automatically alongside the Windows version
- Platform-appropriate fonts, scrolling and icons on macOS and Linux (Windows looks the same as before)

### v1.0.0 — first release

- Today and Full Week views with High / Medium / Low impact news from ForexFactory
- Impact and currency filters
- Timezone picker, remembered between runs
- Notes panel with auto-save and bold / italic formatting
- Light and dark themes with comfortable, high-contrast text
- Local cache for rate-limit protection and offline use
- Announcement strip with automatic rotation
- Windows exe built and published by GitHub Actions

## License

[MIT](LICENSE) · Data: ForexFactory
