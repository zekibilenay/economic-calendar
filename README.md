# Economic Calendar

A free, open-source Windows panel that shows the day's and the week's **High / Medium / Low impact** economic news in one clean window. Data comes from the ForexFactory weekly feed.

No account, no ads, no tracking.

## Features

- **Today** and **Full Week** views, with the next releases highlighted as they approach
- Filter by impact (High / Medium / Low) and by currency
- Timezone picker (UTC−12 … UTC+14) that is remembered between runs
- Notes panel with auto-save and bold / italic (`Ctrl+B` / `Ctrl+I`); drag the divider to resize it
- Light and dark themes, both tuned for comfortable reading
- Optional always-on-top pin
- Works offline from a local cache when the feed can't be reached
- Announcement strip for news about new versions

## Download

1. Open the [Releases](https://github.com/zekibilenay/economic-calendar/releases) page and download the latest `EconomicCalendar-windows.zip`.
2. Extract the zip into a folder.
3. Run `EconomicCalendar.exe`.

### If Windows SmartScreen warns you

The app is not code-signed yet, so Windows may show an "unknown publisher" warning. You can choose **More info → Run anyway**, but you don't have to trust it blindly:

1. **Open source:** [`economic_calendar.py`](economic_calendar.py) is a single readable file.
2. **Built by GitHub Actions:** the exe is built from this repository by [`.github/workflows/build.yml`](.github/workflows/build.yml). To verify:
   `gh attestation verify EconomicCalendar-windows.zip --repo zekibilenay/economic-calendar`
3. **Checksum:** in PowerShell, `Get-FileHash EconomicCalendar-windows.zip` must match the `.sha256` file attached to the release.
4. **No exe at all:** run it from source (below).

## Privacy

- Your notes and settings stay on your computer, in your user folder (`.econ_cal_notes.txt`, `.econ_cal_settings.json`, `.econ_cal_cache_this.json`).
- Network connections:
  1. Calendar data from `nfs.faireconomy.media` (the ForexFactory feed).
  2. One HTTPS GET for the announcement file. No identifiers or personal data are sent; the server only sees `User-Agent: EconomicCalendar/<version>`.

## Run from source

Requires Python 3.9+ (tkinter ships with the Windows installer). No extra packages are needed.

```
python economic_calendar.py
```

`Economic_Calendar.vbs` starts the app without a console window.

To build the exe yourself:

```
pip install pyinstaller
pyinstaller --onedir --windowed --name EconomicCalendar --icon economic_calendar.ico --add-data "economic_calendar.ico;." economic_calendar.py
```

## Announcements

The app reads the shared announcement feed from [zekibilenay/announcements](https://github.com/zekibilenay/announcements). Announcements rotate every 10 seconds when there is more than one. The feed address is `ANNOUNCE_URL` in `economic_calendar.py` (HTTPS only; it can be overridden with the `ECONCAL_ANNOUNCE_URL` environment variable).

## Releasing a new version

1. Update `APP_VERSION` in `economic_calendar.py`.
2. Add a section to **What's new** below.
3. Tag and push:
   ```
   git tag v1.0.1
   git push --tags
   ```

GitHub Actions builds the exe and attaches it to the release.

## What's new

Newest first. Every update gets its own section here.

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
