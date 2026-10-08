#!/usr/bin/env python3
"""
Economic Calendar — Daily & Weekly High/Medium/Low Impact News Panel
Data source : ForexFactory (nfs.faireconomy.media) — last/this/next week
Cache       : local file per week (rate-limit protection, network-error fallback)
Notes       : local file, auto-saved as you type, supports bold/italic (select text, click B/I or Ctrl+B/Ctrl+I)
Timezone    : user-selectable (🌐 menu in the header), remembered across runs
Layout      : notes panel width is remembered across runs
"""

import tkinter as tk
from tkinter import font as tkfont
import urllib.request
import ssl
import json
import re
import os
import time
from datetime import datetime, date, timedelta, timezone
from itertools import groupby
import threading
import sys
import webbrowser
import urllib.error
from tkinter import messagebox

APP_NAME    = "Economic Calendar"
APP_VERSION = "1.0.0"
APP_ID      = "economiccalendar"   # id used in the shared announcement feed
REPO_URL    = "https://github.com/zekibilenay/economic-calendar"

# Shared announcement feed (same JSON file all apps read). HTTPS only.
ANNOUNCE_URL = os.environ.get("ECONCAL_ANNOUNCE_URL",
                              "https://zekibilenay.github.io/announcements/feed.json")
ANNOUNCE_REFRESH_MS = 6 * 60 * 60 * 1000   # re-check every 6 hours while open
ANNOUNCE_ROTATE_MS  = 10_000               # rotation speed when there are several

# ─── Settings ────────────────────────────────────────────────
HOME           = os.path.expanduser("~")
NOTES_FILE     = os.path.join(HOME, ".econ_cal_notes.txt")
SETTINGS_FILE  = os.path.join(HOME, ".econ_cal_settings.json")

CACHE_MAX_AGE  = 30 * 60          # 30 minutes (seconds)
AUTO_REFRESH   = 30 * 60 * 1000   # 30 minutes (ms)
NOTES_SAVE_DELAY = 700             # debounce for notes (ms)

# ForexFactory's free feed for "this week".
WEEK_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CACHE_FILE = os.path.join(HOME, ".econ_cal_cache_this.json")

HEADERS = {
    "User-Agent"     : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept"         : "application/json, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer"        : "https://www.forexfactory.com/",
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode    = ssl.CERT_NONE

EN_DAYS   = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
EN_MONTHS = ["January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]

def format_date_long(d: date) -> str:
    return f"{EN_DAYS[d.weekday()]}, {EN_MONTHS[d.month - 1]} {d.day}, {d.year}"

def format_date_short(d: date) -> str:
    return f"{EN_DAYS[d.weekday()]}  {d.day:02d}.{d.month:02d}"

# ─── Colors / Themes ─────────────────────────────────────────
# Two themes: "light" (default, easier to read) and "dark".
THEMES = {
    "light": dict(
        BG="#f5f6f8", HDR_BG="#ffffff", BAR_BG="#eef0f3", ROW_ALT="#eceff3",
        WARN_BG="#fff3cd", DAY_BG="#e9ecf1", SEP="#d7dce2",
        TXT="#1f2328", TXT_DIM="#535863",
        RED="#ae2a2a", YELLOW="#795400", GREEN="#156c3a", BLUE="#155cad",
        ORANGE="#a14809", PURPLE="#6b3fc0", ACCENT="#1452db", ON_ACCENT="#ffffff",
        NOTES_BG="#ffffff",
    ),
    "dark": dict(
        BG="#161b22", HDR_BG="#1c2330", BAR_BG="#1a202b", ROW_ALT="#1e2530",
        WARN_BG="#3a2d10", DAY_BG="#1c2330", SEP="#2d3542",
        TXT="#e6e9ee", TXT_DIM="#9ea7b1",
        RED="#ff7b7b", YELLOW="#e3b341", GREEN="#3fb950", BLUE="#6cb0ff",
        ORANGE="#f78166", PURPLE="#c49bff", ACCENT="#4c94ff", ON_ACCENT="#0b1220",
        NOTES_BG="#10141b",
    ),
}

IMPACT_LABEL = {"High": "H", "Medium": "M", "Low": "L"}

def apply_theme(name):
    """Updates the module-level color constants to match the selected theme."""
    global BG, HDR_BG, BAR_BG, ROW_ALT, WARN_BG, DAY_BG, SEP, TXT, TXT_DIM, \
           RED, YELLOW, GREEN, BLUE, ORANGE, PURPLE, ACCENT, ON_ACCENT, NOTES_BG, IMPACT_COLOR
    t = THEMES.get(name, THEMES["light"])
    BG, HDR_BG, BAR_BG, ROW_ALT = t["BG"], t["HDR_BG"], t["BAR_BG"], t["ROW_ALT"]
    WARN_BG, DAY_BG, SEP        = t["WARN_BG"], t["DAY_BG"], t["SEP"]
    TXT, TXT_DIM                = t["TXT"], t["TXT_DIM"]
    RED, YELLOW, GREEN, BLUE    = t["RED"], t["YELLOW"], t["GREEN"], t["BLUE"]
    ORANGE, PURPLE, ACCENT      = t["ORANGE"], t["PURPLE"], t["ACCENT"]
    ON_ACCENT                   = t["ON_ACCENT"]
    NOTES_BG                    = t["NOTES_BG"]
    IMPACT_COLOR = {"High": RED, "Medium": YELLOW, "Low": TXT_DIM}

apply_theme("light")

# ─── Cache ───────────────────────────────────────────────────
def cache_age():
    try:
        return time.time() - os.path.getmtime(CACHE_FILE)
    except FileNotFoundError:
        return float("inf")

def load_cache():
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

# ─── Settings (filter preferences) ────────────────────────────
def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f)
    except Exception:
        pass

# ─── Notes ───────────────────────────────────────────────────
# Notes are stored as JSON: {"text": "...", "tags": {"b": [[s,e],...], "i": [...], "bi": [...]}}
# so bold/italic formatting survives restarts. Older plain-text notes
# files (pre-formatting) are still read fine — they just load unstyled.
def load_notes():
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return {"text": "", "tags": {}}
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "text" in data:
            data.setdefault("tags", {})
            return data
    except Exception:
        pass
    return {"text": raw, "tags": {}}   # legacy plain-text notes file

def save_notes(text, tags=None):
    try:
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump({"text": text, "tags": tags or {}}, f)
    except Exception:
        pass

# ─── Timezones ───────────────────────────────────────────────
# Plain, unambiguous fixed UTC offsets (no city/region names, no DST
# guessing — the app can never be "wrong" about which offset is active
# because there's nothing to infer). Label shown in the UI -> offset in
# whole hours from UTC (None = use the system's local time).
def _tz_label(h):
    if h == 0:
        return "UTC"
    return f"UTC{h:+d}"

TIMEZONES = [("System (Local)", None)] + [(_tz_label(h), h) for h in range(-12, 15)]

def resolve_tz(offset_hours):
    """None -> system local time. Otherwise a fixed-offset tzinfo for the
    given whole-hour UTC offset."""
    if offset_hours is None:
        return None
    return timezone(timedelta(hours=offset_hours))

# Some feeds occasionally send a full country name instead of the 3-letter
# currency code. Normalizing these means every region — including Japan —
# is shown the same way as everyone else (e.g. "JPY", not "JAPAN").
COUNTRY_TO_CCY = {
    "JAPAN": "JPY", "JPN": "JPY", "JP": "JPY",
    "UNITED STATES": "USD", "USA": "USD", "US": "USD",
    "EURO ZONE": "EUR", "EUROZONE": "EUR", "EU": "EUR",
    "UNITED KINGDOM": "GBP", "UK": "GBP", "GB": "GBP",
    "CANADA": "CAD", "AUSTRALIA": "AUD", "NEW ZEALAND": "NZD",
    "SWITZERLAND": "CHF", "CHINA": "CNY",
}

# FF tags events that aren't tied to one specific currency (e.g. general
# market holidays) with "ALL" — shown with a clearer Turkish label in the
# currency filter instead of the raw code, since it's not an actual currency.
CURRENCY_DISPLAY = {"ALL": "General (All Markets)"}

# ─── Fetch & Parse Data ────────────────────────────────────────
def parse_dt(s):
    s = re.sub(r'([+-])(\d{2})(\d{2})$', r'\1\2:\3', s)
    return datetime.fromisoformat(s)

def fetch_this_week(force=False):
    """Uses the cache if it's fresh, otherwise fetches from ForexFactory.
    Returns (data, age_seconds, source)."""
    age = cache_age()
    if not force and age < CACHE_MAX_AGE:
        return load_cache(), age, "cache"
    req = urllib.request.Request(WEEK_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as r:
        data = json.loads(r.read().decode("utf-8"))
    save_cache(data)
    return data, 0, "network"

def parse_events(raw_events, tz=None):
    """
    Converts raw FF data into the form the app uses.
    High / Medium / Low impact news is kept (Low is off by default in the
    UI filter — it's what surfaces most Japan/JPY releases, which FF grades
    Low far more often than other major currencies).
    Converted to `tz` (a tzinfo, from resolve_tz), or the system's local
    timezone if tz is None.
    """
    out = []
    for e in raw_events:
        impact = (e.get("impact") or "").strip().title()
        if impact not in ("High", "Medium", "Low"):
            continue
        try:
            dt_utc = parse_dt(e["date"])
            dt_local = dt_utc.astimezone(tz) if tz is not None else dt_utc.astimezone()
        except Exception:
            continue
        raw_ccy = (e.get("country") or "").upper()
        currency = COUNTRY_TO_CCY.get(raw_ccy, raw_ccy)
        out.append({
            "dt"      : dt_local,
            "date"    : dt_local.date(),
            "time"    : dt_local.strftime("%H:%M"),
            "minutes" : dt_local.hour * 60 + dt_local.minute,
            "currency": currency,
            "name"    : e.get("title") or "",
            "impact"  : impact,
            "forecast": e.get("forecast") or "",
            "previous": e.get("previous") or "",
            "actual"  : e.get("actual") or "",
        })
    out.sort(key=lambda x: x["dt"])
    return out

# ─── Announcements (shared feed, same format as Next Book) ───
# English-only app: announcement text always uses the "en" entry of the feed.
# Announcements cannot be dismissed; with several, they rotate automatically.
ANN_LANG      = "en"
ANN_TYPE_ICON = {"update": "⬆", "new_app": "✨", "recommended": "★", "info": "ℹ"}

def parse_version(v):
    parts = re.findall(r"\d+", str(v))
    return tuple(int(x) for x in parts[:4]) or (0,)

def safe_url(u):
    u = str(u or "").strip()
    return u if u.lower().startswith("https://") and len(u) <= 500 else ""

def _loc(value, lang):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get(lang) or value.get("en") or next(
            (x for x in value.values() if isinstance(x, str)), "")
    return ""

def fetch_feed(url):
    if not url.lower().startswith("https://"):
        raise ValueError("announcement url must be https")
    req = urllib.request.Request(url, headers={"User-Agent": f"EconomicCalendar/{APP_VERSION}",
                                               "Accept": "application/json"})
    # Default (verifying) SSL context on purpose — this is not the FF feed.
    with urllib.request.urlopen(req, timeout=6) as r:
        raw = r.read(65537)
    if len(raw) > 65536:
        raise ValueError("announcement feed too large")
    return json.loads(raw.decode("utf-8"))

def select_announcements(feed, app_id, version, lang=ANN_LANG, today=None):
    """Announcements to show for this app + version + language, highest priority first."""
    out = []
    if not isinstance(feed, dict):
        return out
    today = today or date.today()
    cur = parse_version(version)

    apps = feed.get("apps")
    info = apps.get(app_id) if isinstance(apps, dict) else None
    if isinstance(info, dict) and info.get("latest") and parse_version(info["latest"]) > cur:
        out.append({"id": f"update-{app_id}-{info['latest']}", "type": "update", "priority": 1000,
                    "text": f"A new version is out: {info['latest']} (you have {version})",
                    "url": safe_url(info.get("url")) or safe_url(REPO_URL + "/releases/latest")})

    items = feed.get("announcements")
    for a in (items if isinstance(items, list) else []):
        try:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("id") or "")[:80]
            if not aid:
                continue
            targets = a.get("apps", ["*"])
            targets = [targets] if isinstance(targets, str) else list(targets)
            if "*" not in targets and app_id not in targets:
                continue
            if a.get("min_version") and cur < parse_version(a["min_version"]):
                continue
            if a.get("max_version") and cur > parse_version(a["max_version"]):
                continue
            if a.get("starts") and today < date.fromisoformat(str(a["starts"])):
                continue
            if a.get("expires") and today > date.fromisoformat(str(a["expires"])):
                continue
            text = " ".join(_loc(a.get("text"), lang).split())[:300]
            if not text:
                continue
            kind = a.get("type") if a.get("type") in ANN_TYPE_ICON else "info"
            out.append({"id": aid, "type": kind, "text": text,
                        "url": safe_url(a.get("url")), "priority": int(a.get("priority", 0))})
        except (ValueError, TypeError):
            continue   # one broken entry must not block the others
    out.sort(key=lambda x: -x["priority"])
    return out

def resource_path(name):
    """Finds bundled files both when run normally and inside a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

# ─── Scrollable frame ────────────────────────────────────────
class ScrollFrame(tk.Frame):
    """Vertical content area, scrollable with the mouse wheel."""
    def __init__(self, parent, bg=BG, **kw):
        super().__init__(parent, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.vbar   = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner  = tk.Frame(self.canvas, bg=bg)

        self.inner.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        self.canvas.bind("<Enter>", lambda e: self._bind_wheel())
        self.canvas.bind("<Leave>", lambda e: self._unbind_wheel())

    def _bind_wheel(self):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)     # Windows
        self.canvas.bind_all("<Button-4>", self._on_wheel_lin)   # Linux
        self.canvas.bind_all("<Button-5>", self._on_wheel_lin)

    def _unbind_wheel(self):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_wheel_lin(self, event):
        self.canvas.yview_scroll(-1 if event.num == 4 else 1, "units")

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()

# ─── Application ─────────────────────────────────────────────
class EconCalApp:
    COLS    = ["TIME", " ", "CCY", "EVENT",  "FORECAST", "PREVIOUS", "ACTUAL"]
    WIDTHS  = [7,       2,   5,      30,        9,          9,          9   ]
    ANCHORS = ["w",     "w", "w",    "w",       "e",        "e",        "e" ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Economic Calendar")
        self.root.geometry("1060x620")
        self.root.minsize(820, 460)

        self.f_mono  = tkfont.Font(family="Consolas", size=10)
        self.f_ui    = tkfont.Font(family="Segoe UI",  size=9)
        self.f_ui_b  = tkfont.Font(family="Segoe UI",  size=9, weight="bold")
        self.f_ui_i  = tkfont.Font(family="Segoe UI",  size=9, slant="italic")
        self.f_ui_bi = tkfont.Font(family="Segoe UI",  size=9, weight="bold", slant="italic")
        self.f_title = tkfont.Font(family="Segoe UI",  size=11, weight="bold")

        settings = load_settings()

        # Theme: default is "light" (easier on the eyes). "dark" is also available.
        self.theme_name = settings.get("theme", "light")
        apply_theme(self.theme_name)
        self.root.configure(bg=BG)

        # Staying on top is now opt-in (off by default), so clicking another
        # window lets it actually come to the front.
        self.pin_on_top = tk.BooleanVar(value=settings.get("pin_on_top", False))
        self.root.attributes("-topmost", self.pin_on_top.get())

        self.tab            = tk.StringVar(value=settings.get("tab", "today"))
        self.show_high      = tk.BooleanVar(value=settings.get("show_high", True))
        self.show_medium    = tk.BooleanVar(value=settings.get("show_medium", True))
        self.show_low       = tk.BooleanVar(value=settings.get("show_low", False))
        self.selected_countries = set(settings.get("countries", []))  # empty = not yet known
        self._countries_initialized = bool(settings.get("countries_initialized", False))
        self.country_vars   = {}   # currency -> BooleanVar

        self._data_source = "network"

        # Timezone: which UTC offset event/current times are displayed in.
        # None = system's local timezone (previous/default behaviour).
        raw_tz = settings.get("timezone")
        self.tz_offset = raw_tz if isinstance(raw_tz, int) else None
        self.tz_label_by_offset = dict((v, k) for k, v in TIMEZONES)
        self.tz_offset_by_label = dict(TIMEZONES)
        self.tz_var = tk.StringVar(
            value=self.tz_label_by_offset.get(self.tz_offset, TIMEZONES[0][0]))

        # Notes panel width (px), remembered across restarts.
        self.notes_width = int(settings.get("notes_width", 230) or 230)

        # Announcements (always on, cannot be dismissed or disabled by the user).
        self._ann_feed        = None
        self._ann_items       = []
        self._ann_idx         = 0
        self._ann_rotate_job  = None
        self._ann_refresh_job = None

        self.all_events   = []     # parse_events() output (raw, unfiltered)
        self._raw_data    = None   # last raw FF payload (kept to re-parse on tz change)
        self._cache_age   = None
        self._auto_job    = None

        self._build_layout()
        self._refresh(force=False)
        self._tick()
        self._start_announcements()

    # ── Overall layout ──────────────────────────────────────
    def _build_layout(self):
        self._build_header()
        self.ann_holder = tk.Frame(self.root, bg=BG)
        self.ann_holder.pack(fill="x")
        self._build_filterbar()

        # A draggable divider between the calendar (left) and notes (right)
        # panels: the notes panel can now be expanded/collapsed and always
        # stays neatly anchored on the right.
        body = tk.PanedWindow(self.root, orient="horizontal", bg=SEP,
                               sashwidth=5, sashrelief="flat", bd=0,
                               sashpad=0, showhandle=False)
        body.pack(fill="both", expand=True)
        self.body = body

        # Left: calendar (flexible width)
        left = tk.Frame(body, bg=BG)
        self._build_tablehead(left)
        self.scroll = ScrollFrame(left, bg=BG)
        self.scroll.pack(fill="both", expand=True)
        body.add(left, stretch="always", minsize=380)

        # Right: notes (resizable by dragging — width is remembered)
        right = tk.Frame(body, bg=BG)
        self._build_notes(right)
        body.add(right, stretch="never", minsize=180, width=self.notes_width)

        # Whenever the user finishes dragging the divider, remember the
        # notes panel's new width so it opens the same way next time.
        body.bind("<ButtonRelease-1>", self._on_sash_release)

        self._build_footer()
        self._render_announcement()

    def _build_header(self):
        bar = tk.Frame(self.root, bg=HDR_BG)
        bar.pack(fill="x")
        tk.Label(bar, text="  📅  ECONOMIC CALENDAR", bg=HDR_BG, fg=TXT,
                 font=self.f_title, anchor="w").pack(side="left", pady=7, padx=4)
        self.clock_lbl = tk.Label(bar, text="", bg=HDR_BG, fg=BLUE, font=self.f_ui)
        self.clock_lbl.pack(side="right", padx=10)

        tzf = tk.Frame(bar, bg=HDR_BG)
        tzf.pack(side="right", padx=4)
        tk.Label(tzf, text="🌐", bg=HDR_BG, fg=TXT_DIM, font=self.f_ui).pack(side="left")
        self.tz_menu = tk.OptionMenu(tzf, self.tz_var, *[lbl for lbl, _ in TIMEZONES],
                                      command=self._on_timezone_change)
        self.tz_menu.configure(bg=HDR_BG, fg=TXT, relief="flat", bd=0,
                                highlightthickness=0, font=self.f_ui, cursor="hand2",
                                activebackground=BAR_BG, activeforeground=TXT)
        self.tz_menu["menu"].configure(bg=HDR_BG, fg=TXT, font=self.f_ui,
                                        activebackground=ACCENT, activeforeground=ON_ACCENT)
        self.tz_menu.pack(side="left")

        tk.Button(bar, text="↻", bg=HDR_BG, fg=TXT_DIM, relief="flat", bd=0,
                  font=self.f_title, cursor="hand2", activebackground=HDR_BG, activeforeground=TXT,
                  command=lambda: self._refresh(force=True)).pack(side="right", padx=4)
        self.btn_theme = tk.Button(bar, text="🌗", bg=HDR_BG, fg=TXT_DIM, relief="flat", bd=0,
                  font=self.f_title, cursor="hand2", activebackground=HDR_BG, activeforeground=TXT,
                  command=self._toggle_theme)
        self.btn_theme.pack(side="right", padx=4)
        self.btn_pin = tk.Button(bar, text="📌", relief="flat", bd=0,
                  font=self.f_title, cursor="hand2",
                  command=self._toggle_pin)
        self.btn_pin.pack(side="right", padx=4)
        self._style_pin_button()

        tabs = tk.Frame(self.root, bg=HDR_BG)
        tabs.pack(fill="x")
        self.btn_today = tk.Button(tabs, text="  Today  ", relief="flat", bd=0,
                                    font=self.f_ui_b, cursor="hand2",
                                    command=lambda: self._set_tab("today"))
        self.btn_week  = tk.Button(tabs, text="  Full Week  ", relief="flat", bd=0,
                                    font=self.f_ui_b, cursor="hand2",
                                    command=lambda: self._set_tab("week"))
        self.btn_today.pack(side="left", padx=(8, 2), pady=(0, 6))
        self.btn_week.pack(side="left", padx=2, pady=(0, 6))
        self._style_tabs()

        tk.Frame(self.root, bg=SEP, height=1).pack(fill="x")

    # ── Pin (always on top) ─────────────────────────────────
    def _style_pin_button(self):
        on = self.pin_on_top.get()
        self.btn_pin.configure(bg=ACCENT if on else HDR_BG,
                                fg=ON_ACCENT if on else TXT_DIM,
                                activebackground=ACCENT if on else HDR_BG,
                                activeforeground=ON_ACCENT if on else TXT)

    def _toggle_pin(self):
        self.pin_on_top.set(not self.pin_on_top.get())
        self.root.attributes("-topmost", self.pin_on_top.get())
        self._style_pin_button()
        self._persist_settings()

    # ── Timezone ──────────────────────────────────────────────
    def _now(self):
        """Current time in the user's selected UTC offset (or system local)."""
        tz = resolve_tz(self.tz_offset)
        return datetime.now(tz) if tz is not None else datetime.now()

    def _on_timezone_change(self, label):
        self.tz_offset = self.tz_offset_by_label.get(label)
        self._persist_settings()
        # Re-parse the already-fetched data in the newly selected timezone
        # instead of hitting the network again.
        if self._raw_data is not None:
            self.all_events = parse_events(self._raw_data, tz=resolve_tz(self.tz_offset))
            self._rebuild_country_filters()
        self._render()
        self._update_footer()

    # ── Toggle theme (light / dark) ─────────────────────────
    def _toggle_theme(self):
        new_theme = "dark" if self.theme_name == "light" else "light"
        # Grab any unsaved notes text (and its bold/italic formatting)
        # first so it isn't lost when the widgets are rebuilt, then write
        # it back afterwards.
        try:
            notes_content = self.notes_txt.get("1.0", "end-1c")
            notes_tags = self._notes_tag_state()
        except Exception:
            notes_content = None
            notes_tags = {}

        self.theme_name = new_theme
        apply_theme(new_theme)
        self._persist_settings()

        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=BG)
        self._build_layout()

        if notes_content is not None:
            self.notes_txt.delete("1.0", "end")
            self.notes_txt.insert("1.0", notes_content)
            for tagname, pairs in notes_tags.items():
                for s, e in pairs:
                    self.notes_txt.tag_add(tagname, s, e)
            self.notes_txt.edit_modified(False)

        self._style_pin_button()
        self._rebuild_country_filters()
        self._render()
        self._update_footer()

    def _style_tabs(self):
        active, inactive = ACCENT, HDR_BG
        for name, btn in (("today", self.btn_today), ("week", self.btn_week)):
            on = self.tab.get() == name
            btn.configure(bg=active if on else inactive,
                          fg=ON_ACCENT if on else TXT_DIM,
                          activebackground=active if on else inactive,
                          activeforeground=ON_ACCENT if on else TXT)

    def _set_tab(self, name):
        self.tab.set(name)
        self._style_tabs()
        self._persist_settings()
        self._render()

    def _build_filterbar(self):
        bar = tk.Frame(self.root, bg=BAR_BG)
        bar.pack(fill="x")

        impf = tk.Frame(bar, bg=BAR_BG)
        impf.pack(side="left", padx=8, pady=4)
        tk.Label(impf, text="Impact:", bg=BAR_BG, fg=TXT_DIM, font=self.f_ui).pack(side="left", padx=(0, 4))
        tk.Checkbutton(impf, text="High", variable=self.show_high, command=self._on_filter_change,
                        bg=BAR_BG, fg=RED, selectcolor=BAR_BG, activebackground=BAR_BG, activeforeground=RED,
                        font=self.f_ui, cursor="hand2").pack(side="left")
        tk.Checkbutton(impf, text="Medium", variable=self.show_medium, command=self._on_filter_change,
                        bg=BAR_BG, fg=YELLOW, selectcolor=BAR_BG, activebackground=BAR_BG, activeforeground=YELLOW,
                        font=self.f_ui, cursor="hand2").pack(side="left")
        tk.Checkbutton(impf, text="Low", variable=self.show_low, command=self._on_filter_change,
                        bg=BAR_BG, fg=TXT_DIM, selectcolor=BAR_BG, activebackground=BAR_BG, activeforeground=TXT_DIM,
                        font=self.f_ui, cursor="hand2").pack(side="left")

        tk.Frame(bar, bg=SEP, width=1).pack(side="left", fill="y", padx=6, pady=4)

        self.country_bar = tk.Frame(bar, bg=BAR_BG)
        self.country_bar.pack(side="left", padx=4, pady=4, fill="x", expand=True)
        tk.Label(self.country_bar, text="Currency:", bg=BAR_BG, fg=TXT_DIM,
                 font=self.f_ui).pack(side="left", padx=(0, 4))
        # Kept right next to the label (not at the far right of the window)
        # so they're always visible no matter how many currencies the
        # checkbox list expands to.
        tk.Button(self.country_bar, text="Select All", font=self.f_ui, relief="flat",
                  bg=HDR_BG, fg=TXT_DIM, cursor="hand2",
                  activebackground=BAR_BG, activeforeground=TXT,
                  command=self._select_all_countries).pack(side="left", padx=2)
        tk.Button(self.country_bar, text="Clear All", font=self.f_ui, relief="flat",
                  bg=HDR_BG, fg=TXT_DIM, cursor="hand2",
                  activebackground=BAR_BG, activeforeground=TXT,
                  command=self._select_no_countries).pack(side="left", padx=(2, 8))
        self.country_chk_area = tk.Frame(self.country_bar, bg=BAR_BG)
        self.country_chk_area.pack(side="left", fill="x", expand=True)

        tk.Frame(self.root, bg=SEP, height=1).pack(fill="x")

    def _build_tablehead(self, parent):
        hdr = tk.Frame(parent, bg=HDR_BG)
        hdr.pack(fill="x")
        for name, w, anc in zip(self.COLS, self.WIDTHS, self.ANCHORS):
            # Same font as the data rows (mono) — `width=` is measured in
            # character units of whatever font the Label uses, so mixing a
            # proportional header font with the monospace data font made the
            # pixel widths drift apart, which is what was misaligning the
            # FORECAST/PREVIOUS/ACTUAL columns from their data.
            tk.Label(hdr, text=name, bg=HDR_BG, fg=TXT_DIM, font=self.f_mono,
                     width=w, anchor=anc, padx=6, pady=3).pack(side="left")
        tk.Frame(parent, bg=SEP, height=1).pack(fill="x")

    def _build_notes(self, parent):
        head = tk.Frame(parent, bg=HDR_BG)
        head.pack(fill="x")
        tk.Label(head, text="  📝 NOTES", bg=HDR_BG, fg=TXT, font=self.f_title,
                 anchor="w").pack(side="left", pady=6)
        self.notes_status = tk.Label(head, text="", bg=HDR_BG, fg=GREEN, font=self.f_ui)
        self.notes_status.pack(side="right", padx=6)
        # Bold / italic toggle buttons for the selected notes text
        # (also reachable via Ctrl+B / Ctrl+I).
        self.btn_italic = tk.Button(head, text="I", font=self.f_ui_i, width=2, relief="flat",
                                     bg=HDR_BG, fg=TXT, activebackground=BAR_BG, activeforeground=TXT, cursor="hand2",
                                     command=lambda: self._notes_toggle_style("italic"))
        self.btn_italic.pack(side="right", padx=(0, 2))
        self.btn_bold = tk.Button(head, text="B", font=self.f_ui_b, width=2, relief="flat",
                                   bg=HDR_BG, fg=TXT, activebackground=BAR_BG, activeforeground=TXT, cursor="hand2",
                                   command=lambda: self._notes_toggle_style("bold"))
        self.btn_bold.pack(side="right", padx=(6, 2))
        tk.Frame(parent, bg=SEP, height=1).pack(fill="x")

        txt_wrap = tk.Frame(parent, bg=BG)
        txt_wrap.pack(fill="both", expand=True, padx=6, pady=6)
        # Notes background now follows the active theme instead of being
        # hard-coded, so it stays readable in both light and dark mode.
        self.notes_txt = tk.Text(txt_wrap, bg=NOTES_BG, fg=TXT, insertbackground=TXT,
                                  relief="flat", wrap="word", font=self.f_ui,
                                  undo=True, padx=6, pady=6)
        nsb = tk.Scrollbar(txt_wrap, command=self.notes_txt.yview)
        self.notes_txt.configure(yscrollcommand=nsb.set)
        self.notes_txt.pack(side="left", fill="both", expand=True)
        nsb.pack(side="right", fill="y")

        # Style tags: "b" bold, "i" italic, "bi" bold+italic — mutually
        # exclusive per character, combined as needed.
        self.notes_txt.tag_configure("b", font=self.f_ui_b)
        self.notes_txt.tag_configure("i", font=self.f_ui_i)
        self.notes_txt.tag_configure("bi", font=self.f_ui_bi)

        data = load_notes()
        self.notes_txt.insert("1.0", data.get("text", ""))
        for tagname, pairs in data.get("tags", {}).items():
            for s, e in pairs:
                self.notes_txt.tag_add(tagname, s, e)

        self._notes_save_job = None
        self.notes_txt.bind("<<Modified>>", self._on_notes_modified)
        self.notes_txt.bind("<Control-b>", self._notes_bold_shortcut)
        self.notes_txt.bind("<Control-B>", self._notes_bold_shortcut)
        self.notes_txt.bind("<Control-i>", self._notes_italic_shortcut)
        self.notes_txt.bind("<Control-I>", self._notes_italic_shortcut)

    # ── Notes panel width (remembered across restarts) ─────────
    def _on_sash_release(self, event=None):
        try:
            sash_x = self.body.sash_coord(0)[0]
            total_w = self.body.winfo_width()
            sash_w = int(self.body.cget("sashwidth"))
            new_w = total_w - sash_x - sash_w
            if new_w >= 150:
                self.notes_width = int(new_w)
                self._persist_settings()
        except Exception:
            pass

    def _build_footer(self):
        self.footer = tk.Label(self.root, text="", bg=HDR_BG, fg=TXT_DIM, font=self.f_ui,
                                anchor="e", padx=8, pady=3)
        self.footer.pack(fill="x")

    # ── Notes: bold / italic formatting ─────────────────────────
    def _notes_bold_shortcut(self, event=None):
        self._notes_toggle_style("bold")
        return "break"

    def _notes_italic_shortcut(self, event=None):
        self._notes_toggle_style("italic")
        return "break"

    def _notes_toggle_style(self, kind):
        """Toggle bold or italic on the current notes selection. The style
        at the start of the selection decides whether the whole selection
        gets the style added or removed, so a click always does one clear
        thing rather than fighting a mixed-formatting selection."""
        try:
            sel_start = self.notes_txt.index("sel.first")
            sel_end   = self.notes_txt.index("sel.last")
        except tk.TclError:
            return  # nothing selected

        tags_here = self.notes_txt.tag_names(sel_start)
        has_bold   = "b" in tags_here or "bi" in tags_here
        has_italic = "i" in tags_here or "bi" in tags_here

        if kind == "bold":
            new_bold, new_italic = not has_bold, has_italic
        else:
            new_bold, new_italic = has_bold, not has_italic

        for t in ("b", "i", "bi"):
            self.notes_txt.tag_remove(t, sel_start, sel_end)
        if new_bold and new_italic:
            self.notes_txt.tag_add("bi", sel_start, sel_end)
        elif new_bold:
            self.notes_txt.tag_add("b", sel_start, sel_end)
        elif new_italic:
            self.notes_txt.tag_add("i", sel_start, sel_end)

        self.notes_txt.edit_modified(True)  # feeds the normal autosave path

    # ── Notes: auto-save ─────────────────────────────────────
    def _on_notes_modified(self, event=None):
        if not self.notes_txt.edit_modified():
            return
        self.notes_txt.edit_modified(False)
        if self._notes_save_job:
            self.root.after_cancel(self._notes_save_job)
        self.notes_status.config(text="saving…", fg=TXT_DIM)
        self._notes_save_job = self.root.after(NOTES_SAVE_DELAY, self._save_notes_now)

    def _notes_tag_state(self):
        """Collect current bold/italic tag ranges as plain (start, end) string pairs."""
        tags = {}
        for t in ("b", "i", "bi"):
            ranges = self.notes_txt.tag_ranges(t)
            pairs = [(str(ranges[i]), str(ranges[i + 1])) for i in range(0, len(ranges), 2)]
            if pairs:
                tags[t] = pairs
        return tags

    def _save_notes_now(self):
        content = self.notes_txt.get("1.0", "end-1c")
        save_notes(content, self._notes_tag_state())
        self.notes_status.config(text="✓ saved", fg=GREEN)
        self._notes_save_job = None

    # ── Announcements ─────────────────────────────────────────
    def _start_announcements(self):
        if not ANNOUNCE_URL:
            return
        threading.Thread(target=self._ann_worker, daemon=True).start()

    def _ann_worker(self):
        # Background thread: only touch Tk via root.after(0, ...)
        try:
            feed = fetch_feed(ANNOUNCE_URL)
            self.root.after(0, lambda: self._on_feed_loaded(feed))
        except Exception:
            pass   # announcements are optional — never bother the user with errors
        finally:
            try:
                self.root.after(0, self._schedule_ann_refresh)
            except Exception:
                pass

    def _schedule_ann_refresh(self):
        if self._ann_refresh_job:
            self.root.after_cancel(self._ann_refresh_job)
        self._ann_refresh_job = self.root.after(ANNOUNCE_REFRESH_MS, self._start_announcements)

    def _on_feed_loaded(self, feed):
        self._ann_feed = feed
        self._reselect_announcements()

    def _reselect_announcements(self):
        self._ann_items = select_announcements(self._ann_feed, APP_ID, APP_VERSION)
        self._ann_idx = 0
        self._render_announcement()

    def _render_announcement(self):
        """Draws (or hides) the slim announcement strip under the header."""
        if self._ann_rotate_job:
            try:
                self.root.after_cancel(self._ann_rotate_job)
            except Exception:
                pass
            self._ann_rotate_job = None
        for w in self.ann_holder.winfo_children():
            w.destroy()
        if not self._ann_items:
            return
        self._ann_idx %= len(self._ann_items)
        item = self._ann_items[self._ann_idx]

        strip = tk.Frame(self.ann_holder, bg=BAR_BG)
        strip.pack(fill="x")
        tk.Frame(strip, bg=ACCENT, width=4).pack(side="left", fill="y")

        tk.Label(strip, text=ANN_TYPE_ICON.get(item["type"], "ℹ"), bg=BAR_BG, fg=ACCENT,
                 font=self.f_ui_b).pack(side="left", padx=(10, 6), pady=6)

        if len(self._ann_items) > 1:
            tk.Label(strip, text=f"{self._ann_idx + 1}/{len(self._ann_items)}", bg=BAR_BG,
                     fg=TXT_DIM, font=self.f_ui).pack(side="right", padx=(4, 12))

        txt = tk.Label(strip, text=item["text"], bg=BAR_BG, fg=TXT, font=self.f_ui,
                       anchor="w", justify="left")
        txt.pack(side="left", fill="x", expand=True, pady=6)
        strip.bind("<Configure>", lambda e: txt.configure(wraplength=max(200, e.width - 110)))
        if item["url"]:
            txt.configure(cursor="hand2", fg=ACCENT)
            txt.bind("<Button-1>", lambda e, u=item["url"]: self._open_announcement_url(u))

        tk.Frame(self.ann_holder, bg=SEP, height=1).pack(fill="x")

        if len(self._ann_items) > 1:
            self._ann_rotate_job = self.root.after(ANNOUNCE_ROTATE_MS, self._rotate_announcement)

    def _rotate_announcement(self):
        self._ann_rotate_job = None
        if len(self._ann_items) > 1:
            self._ann_idx = (self._ann_idx + 1) % len(self._ann_items)
            self._render_announcement()

    def _open_announcement_url(self, url):
        if messagebox.askyesno(APP_NAME, f"Open this link in your browser?\n{url}"):
            webbrowser.open(url)

    # ── Clock ─────────────────────────────────────────────────
    def _tick(self):
        now = self._now()
        self.clock_lbl.config(text=f"🕐  {now.strftime('%H:%M')}  ")
        self.root.after(20_000, self._tick)

    # ── Persist settings ─────────────────────────────────────
    def _persist_settings(self):
        save_settings({
            "tab": self.tab.get(),
            "show_high": self.show_high.get(),
            "show_medium": self.show_medium.get(),
            "show_low": self.show_low.get(),
            "countries": sorted(c for c, v in self.country_vars.items() if v.get()),
            "countries_initialized": True,
            "theme": self.theme_name,
            "pin_on_top": self.pin_on_top.get(),
            "timezone": self.tz_offset,
            "notes_width": self.notes_width,
        })

    def _on_filter_change(self):
        self._persist_settings()
        self._render()

    def _select_all_countries(self):
        for v in self.country_vars.values():
            v.set(True)
        self._on_filter_change()

    def _select_no_countries(self):
        for v in self.country_vars.values():
            v.set(False)
        self._on_filter_change()

    # ── Build currency checkboxes from the data ──────────────
    def _rebuild_country_filters(self):
        currencies = sorted({e["currency"] for e in self.all_events if e["currency"]})
        existing = set(self.country_vars.keys())
        incoming = set(currencies)

        # Clean up ones no longer present in the data
        for c in existing - incoming:
            del self.country_vars[c]

        first_time = not self._countries_initialized
        for c in currencies:
            if c not in self.country_vars:
                default_on = True if first_time else (c in self.selected_countries or not self._countries_initialized)
                self.country_vars[c] = tk.BooleanVar(value=default_on)

        self._countries_initialized = True

        for w in self.country_chk_area.winfo_children():
            w.destroy()
        for c in currencies:
            tk.Checkbutton(self.country_chk_area, text=CURRENCY_DISPLAY.get(c, c),
                            variable=self.country_vars[c],
                            command=self._on_filter_change, bg=BAR_BG, fg=TXT,
                            selectcolor=BAR_BG, activebackground=BAR_BG, activeforeground=TXT,
                            font=self.f_ui, cursor="hand2").pack(side="left", padx=2)

    # ── Refresh (from network / cache) ────────────────────────
    def _refresh(self, force=False):
        if self._auto_job:
            self.root.after_cancel(self._auto_job)
            self._auto_job = None

        self.scroll.clear()
        src = "Fetching from ForexFactory..." if force or cache_age() >= CACHE_MAX_AGE \
              else "Loading from cache..."
        tk.Label(self.scroll.inner, text=f"⟳  {src}", bg=BG, fg=TXT_DIM,
                 font=self.f_ui, pady=22).pack()

        threading.Thread(target=self._worker, args=(force,), daemon=True).start()

    def _worker(self, force):
        # NOTE: this runs on a background thread. Tkinter is not thread-safe,
        # so every UI touch (including scheduling with `.after`) must be
        # marshalled back onto the main thread via self.root.after(0, ...) —
        # calling it directly from here was the source of the intermittent
        # errors seen before.
        try:
            data, age, source = fetch_this_week(force=force)
            self._cache_age = age
            self._data_source = source
            self._raw_data = data
            self.all_events = parse_events(data, tz=resolve_tz(self.tz_offset))
            self.root.after(0, self._on_data_loaded)
        except Exception as ex:
            msg = str(ex)
            self.root.after(0, lambda: self._show_error(msg))
        finally:
            self.root.after(0, self._schedule_auto_refresh)

    def _schedule_auto_refresh(self):
        if self._auto_job:
            self.root.after_cancel(self._auto_job)
        self._auto_job = self.root.after(AUTO_REFRESH, lambda: self._refresh(force=True))

    def _on_data_loaded(self):
        self._rebuild_country_filters()
        self._render()
        self._update_footer()

    # ── Error state ───────────────────────────────────────────
    def _show_error(self, msg):
        try:
            data = load_cache()
            self._raw_data = data
            self._data_source = "cache"
            self.all_events = parse_events(data, tz=resolve_tz(self.tz_offset))
            if self.all_events:
                self._rebuild_country_filters()
                self.scroll.clear()
                tk.Label(self.scroll.inner, text="⚠  Network error — showing last cached data",
                         bg=BG, fg=YELLOW, font=self.f_ui, pady=6).pack(anchor="w", padx=6)
                self._render(keep_status=True)
                self._update_footer(from_cache=True)
                return
        except Exception:
            pass

        self.scroll.clear()
        tk.Label(self.scroll.inner, text="⚠  Connection failed", bg=BG, fg=ORANGE,
                 font=tkfont.Font(family="Segoe UI", size=10, weight="bold"),
                 pady=12).pack()
        tk.Label(self.scroll.inner, text=msg, bg=BG, fg=TXT_DIM, font=self.f_ui,
                 pady=4, wraplength=520, justify="left").pack(padx=12)
        tk.Button(self.scroll.inner, text="  Retry  ", bg=HDR_BG, fg=TXT, relief="flat",
                  font=self.f_ui, cursor="hand2", pady=4,
                  activebackground=BAR_BG, activeforeground=TXT,
                  command=lambda: self._refresh(force=True)).pack(pady=12)
        self.footer.config(text="Last refresh failed  ")

    # ── Apply filters ──────────────────────────────────────────
    def _filtered(self):
        allowed_impact = set()
        if self.show_high.get():
            allowed_impact.add("High")
        if self.show_medium.get():
            allowed_impact.add("Medium")
        if self.show_low.get():
            allowed_impact.add("Low")

        allowed_ccy = {c for c, v in self.country_vars.items() if v.get()}

        out = [e for e in self.all_events
               if e["impact"] in allowed_impact and e["currency"] in allowed_ccy]
        return out

    # ── Render ────────────────────────────────────────────────
    def _render(self, keep_status=False):
        events = self._filtered()
        self.scroll.clear()

        today = self._now().date()
        if self.tab.get() == "today":
            todays = [e for e in events if e["date"] == today]
            if not todays:
                tk.Label(self.scroll.inner, text="No news today for the selected filters  🎉",
                         bg=BG, fg=TXT_DIM, font=self.f_ui, pady=24).pack()
            else:
                self._render_rows(todays, today)
        else:
            if not events:
                tk.Label(self.scroll.inner, text="No news this week for the selected filters  🎉",
                         bg=BG, fg=TXT_DIM, font=self.f_ui, pady=24).pack()
            else:
                for day, day_events in groupby(events, key=lambda e: e["date"]):
                    self._render_day_header(day, today)
                    self._render_rows(list(day_events), today)

        if not keep_status:
            self._update_footer()

    def _render_day_header(self, day, today):
        label = format_date_long(day)
        if day == today:
            label += "   •   TODAY"
        fg = BLUE if day == today else TXT_DIM
        row = tk.Frame(self.scroll.inner, bg=DAY_BG)
        row.pack(fill="x", pady=(6, 0))
        tk.Label(row, text="  " + label, bg=DAY_BG, fg=fg, font=self.f_ui_b,
                 anchor="w", pady=4).pack(fill="x")
        tk.Frame(self.scroll.inner, bg=SEP, height=1).pack(fill="x")

    def _render_rows(self, events, today):
        now = self._now()
        now_min = now.hour * 60 + now.minute

        for i, ev in enumerate(events):
            is_today  = ev["date"] == today
            is_future_day = ev["date"] > today
            passed    = (ev["date"] < today) or (is_today and now_min > ev["minutes"])
            upcoming  = is_today and 0 <= (ev["minutes"] - now_min) <= 30 and not passed

            row_bg  = WARN_BG if upcoming else (ROW_ALT if i % 2 else BG)
            txt_col = TXT_DIM if passed else TXT

            if passed:
                time_col = TXT_DIM
            elif upcoming:
                time_col = YELLOW
            elif is_future_day:
                time_col = BLUE
            else:
                time_col = RED

            act_col = GREEN if ev["actual"] else TXT_DIM
            act_txt = ev["actual"] if ev["actual"] else "—"
            fc_txt  = ev["forecast"] if ev["forecast"] else "—"
            pv_txt  = ev["previous"] if ev["previous"] else "—"

            row = tk.Frame(self.scroll.inner, bg=row_bg)
            row.pack(fill="x")

            marker = "▶ " if upcoming else ("✓ " if passed else "  ")
            imp_dot = IMPACT_LABEL.get(ev["impact"], "?")
            imp_col = IMPACT_COLOR.get(ev["impact"], TXT_DIM)
            if passed:
                imp_col = TXT_DIM

            vals = [marker + ev["time"], imp_dot, ev["currency"], ev["name"], fc_txt, pv_txt, act_txt]
            fgs  = [time_col, imp_col, txt_col, txt_col, txt_col, txt_col, act_col]

            for val, fg, w, anc in zip(vals, fgs, self.WIDTHS, self.ANCHORS):
                tk.Label(row, text=val, bg=row_bg, fg=fg, font=self.f_mono,
                         width=w, anchor=anc, padx=6, pady=6).pack(side="left")

            tk.Frame(self.scroll.inner, bg=SEP, height=1).pack(fill="x")

    def _update_footer(self, from_cache=False):
        now = self._now().strftime("%H:%M")
        age = self._cache_age
        if from_cache or self._data_source == "cache" or (age and age > 5):
            src = "cache"
        else:
            src = "ForexFactory"
        age_str = f"{int(age/60)} min ago  |  " if age and age > 60 else ""
        n_shown = len(self._filtered())
        tz_label = self.tz_label_by_offset.get(self.tz_offset, TIMEZONES[0][0])
        self.footer.config(
            text=f"{n_shown} events shown  |  Last updated: {now} ({tz_label})  |  "
                 f"{age_str}Source: {src}  |  Auto-refreshes every 30 min  "
        )

# ─── Start ───────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    try:
        root.iconbitmap(resource_path("economic_calendar.ico"))
    except Exception:
        pass
    app = EconCalApp(root)
    root.mainloop()
