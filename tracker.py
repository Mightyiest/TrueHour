"""
TrueHour — Core tracking engine.
Monitors the active foreground window and records app usage durations.
Includes tamper-resistant time tracking with monotonic clocks and hash chaining.
"""

import time
import threading
import sys
import ctypes as _ctypes

def _get_idle_seconds():
    """Return seconds since last mouse/keyboard input (cross-platform)."""
    if sys.platform == "win32":
        try:
            class _LASTINPUTINFO(_ctypes.Structure):
                _fields_ = [("cbSize", _ctypes.c_uint), ("dwTime", _ctypes.c_uint)]
            lii = _LASTINPUTINFO()
            lii.cbSize = _ctypes.sizeof(_LASTINPUTINFO)
            _ctypes.windll.user32.GetLastInputInfo(_ctypes.byref(lii))
            millis = (_ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF
            return millis / 1000.0
        except Exception:
            return 0.0
    elif sys.platform == "darwin":
        try:
            # Load CoreGraphics library via ctypes (requires no extra python packages)
            import ctypes.util
            lib_path = ctypes.util.find_library("CoreGraphics")
            if not lib_path:
                lib_path = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
            cg = _ctypes.CDLL(lib_path)
            
            # CGEventSourceSecondsSinceLastEventType is double CGEventSourceSecondsSinceLastEventType(int, int)
            cg.CGEventSourceSecondsSinceLastEventType.restype = _ctypes.c_double
            cg.CGEventSourceSecondsSinceLastEventType.argtypes = [_ctypes.c_int32, _ctypes.c_uint32]
            
            # kCGEventSourceStateCombinedSessionState = 0
            # kCGAnyInputEventType = ~0 (0xFFFFFFFF)
            idle_seconds = cg.CGEventSourceSecondsSinceLastEventType(0, 0xFFFFFFFF)
            return float(idle_seconds)
        except Exception:
            # Fallback to Quartz (PyObjC) if ctypes CoreGraphics load failed
            try:
                from Quartz import CGEventSourceSecondsSinceLastEventType, kCGEventSourceStateCombinedSessionState, kCGAnyInputEventType
                return float(CGEventSourceSecondsSinceLastEventType(kCGEventSourceStateCombinedSessionState, kCGAnyInputEventType))
            except Exception:
                return 0.0
    return 0.0



import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from appinfo import get_foreground_app_info
from config import get_app_data_dir
from secure_time import get_detector, reset_detector

# Configure logging for security events
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)

# ── Auto-Exclusion Setup ──────────────────────────────────────────────

# Default auto-excluded apps written on first launch only.
# User edits to the file are never overwritten.
import platform as _platform
_SYSTEM = _platform.system()

if _SYSTEM == "Darwin":
    _DEFAULT_AUTO_EXCLUDED = """\
# ══════════════════════════════════════════════════════════════════
# TrueHour — Auto-Excluded Apps (macOS)
# ══════════════════════════════════════════════════════════════════
# Apps listed here are completely invisible to TrueHour.
# They will not appear in the app list, report, timeline, or CSV.
#
# Rules:
#   - One application name or process name per line (e.g. Finder)
#   - Lines starting with # are comments and are ignored
#   - Names are case-insensitive
#
# To stop excluding an app, delete its line or add # in front.
# To exclude a new app, add its name on a new line.
# Changes take effect on the next session start.
# ══════════════════════════════════════════════════════════════════

# ── macOS Core System UI & Desktop ─────────────────────────────────
Finder
Dock
SystemUIServer
loginwindow
NotificationCenter
ControlCenter
Spotlight
WindowManager

# ── macOS Utilities (brief use, not real work) ────────────────────
Activity Monitor
Terminal
Console
System Settings
System Preferences
Keychain Access
Screen Sharing

# ── Audio & Core services ─────────────────────────────────────────
coreaudiod
screencapture
"""
else:
    _DEFAULT_AUTO_EXCLUDED = """\
# ══════════════════════════════════════════════════════════════════
# TrueHour — Auto-Excluded Apps
# ══════════════════════════════════════════════════════════════════
# Apps listed here are completely invisible to TrueHour.
# They will not appear in the app list, report, timeline, or CSV.
#
# Rules:
#   - One executable name per line (e.g. explorer.exe)
#   - Lines starting with # are comments and are ignored
#   - Names are case-insensitive
#   - .exe extension is optional
#
# To stop excluding an app, delete its line or add # in front.
# To exclude a new app, add its .exe name on a new line.
# Changes take effect on the next session start.
# ══════════════════════════════════════════════════════════════════

# ── Windows Shell & Desktop ────────────────────────────────────────
explorer.exe
dwm.exe
shellexperiencehost.exe
applicationframehost.exe
startmenuexperiencehost.exe
searchhost.exe
searchindexer.exe
searchapp.exe
widgets.exe
textinputhost.exe

# ── Snipping & Screenshot Tools ───────────────────────────────────
snipping.exe
snippingtool.exe
screensketch.exe

# ── System Services & Background ──────────────────────────────────
svchost.exe
csrss.exe
wininit.exe
winlogon.exe
lsass.exe
services.exe
rundll32.exe
taskhostw.exe
spoolsv.exe
fontdriverhost.exe
sihost.exe
ctfmon.exe

# ── Windows Updates & Maintenance ─────────────────────────────────
tiworker.exe
trustedinstaller.exe
mrt.exe
wuauclt.exe
usoclient.exe

# ── Windows Defender & Security ───────────────────────────────────
msmpeng.exe
nissrv.exe
securityhealthsystray.exe
securityhealthservice.exe
smartscreen.exe

# ── Audio & Volume ────────────────────────────────────────────────
sndvol.exe
audiodg.exe
realtek.exe

# ── Input & Language ──────────────────────────────────────────────
TabTip.exe
InputMethod.exe

# ── System Utilities (brief use, not real work) ───────────────────
taskmgr.exe
dxdiag.exe
msinfo32.exe
msiexec.exe
consent.exe

# ── Quick Calculators & Clocks (optional) ─────────────────────────
# Uncomment below if you want to exclude these:
# calculator.exe
# calc.exe
# clock.exe

# ── Terminal / Command Line ───────────────────────────────────────
# These are commented out by default because developers may use them.
# Uncomment to exclude:
# cmd.exe
# powershell.exe
# pwsh.exe
# windowsterminal.exe
# conhost.exe

# ── Development Runtimes ──────────────────────────────────────────
# Commented out — uncomment if these run silently in background for you:
# python.exe
# pythonw.exe
# node.exe
# docker.exe
"""

AUTO_EXCLUDE_FILE = os.path.join(get_app_data_dir(), "auto_excluded_apps.txt")
ACTIVE_SESSION_FILE = os.path.join(get_app_data_dir(), "active_session.json")

_AUTO_EXCLUDED_EXES = set()  # must be declared before any function references it
_AUTO_EXCLUDED_LOCK = threading.Lock()  # thread-safe access to _AUTO_EXCLUDED_EXES


def create_auto_excluded_if_missing():
    """Generate default auto_excluded_apps.txt on first launch only.
    If file already exists, make sure all default system apps are present, but don't overwrite user edits."""
    if os.path.exists(AUTO_EXCLUDE_FILE):
        try:
            with open(AUTO_EXCLUDE_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            content_lower = content.lower()
            
            # Extract all default active executables/apps from _DEFAULT_AUTO_EXCLUDED
            default_apps = []
            is_windows = _platform.system() == "Windows"
            for line in _DEFAULT_AUTO_EXCLUDED.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    exe = line.lower()
                    if is_windows and not exe.endswith(".exe"):
                        exe += ".exe"
                    default_apps.append((line, exe))
            
            missing_additions = []
            for raw_name, exe_name in default_apps:
                base_name = exe_name[:-4] if (is_windows and exe_name.endswith(".exe")) else exe_name
                # Check if this app/process is present in the file
                if base_name not in content_lower:
                    missing_additions.append(raw_name)
                
            if missing_additions:
                with open(AUTO_EXCLUDE_FILE, "a", encoding="utf-8") as f:
                    f.write("\n# ── Automatically Excluded Apps (Added via update) ──\n")
                    for app in missing_additions:
                        f.write(f"{app}\n")
        except Exception as e:
            logger.warning(f"Failed to check/update existing auto-exclude file: {e}")
        return
    try:
        dirpath = os.path.dirname(AUTO_EXCLUDE_FILE)
        if dirpath:
            # Validate directory path to prevent path traversal
            abs_dir = os.path.abspath(dirpath)
            app_data_dir = os.path.abspath(get_app_data_dir())
            if not abs_dir.startswith(app_data_dir):
                logger.error(f"Invalid auto-exclude directory path: {dirpath}")
                return
            os.makedirs(dirpath, exist_ok=True)
        with open(AUTO_EXCLUDE_FILE, "w", encoding="utf-8") as f:
            f.write(_DEFAULT_AUTO_EXCLUDED)
    except OSError as e:
        logger.warning(f"Failed to create auto-exclude file: {e}")


def _load_auto_excluded():
    """Load auto_excluded_apps.txt into _AUTO_EXCLUDED_EXES set."""
    global _AUTO_EXCLUDED_EXES
    _AUTO_EXCLUDED_EXES = set()  # reset before loading
    if not os.path.exists(AUTO_EXCLUDE_FILE):
        return
    try:
        # Validate file path to prevent path traversal
        abs_file = os.path.abspath(AUTO_EXCLUDE_FILE)
        app_data_dir = os.path.abspath(get_app_data_dir())
        if not abs_file.startswith(app_data_dir):
            logger.error(f"Invalid auto-exclude file path: {AUTO_EXCLUDE_FILE}")
            return
        with open(AUTO_EXCLUDE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().lower()
                if line and not line.startswith("#") and line[0].isalnum():
                    if not line.endswith(".exe"):
                        line += ".exe"
                    _AUTO_EXCLUDED_EXES.add(line)
    except (OSError, IOError) as e:
        logger.warning(f"Failed to load auto-exclude file: {e}")


def reload_auto_excluded(lock=None):
    """
    Reload auto_excluded_apps.txt into _AUTO_EXCLUDED_EXES.
    Thread-safe: pass the tracker's _lock if called while session is running.

    Changes take effect on the next app switch in _poll_loop.
    The currently tracked app is never interrupted.
    """
    global _AUTO_EXCLUDED_EXES

    new_set = set()
    if os.path.exists(AUTO_EXCLUDE_FILE):
        try:
            # Validate file path to prevent path traversal
            abs_file = os.path.abspath(AUTO_EXCLUDE_FILE)
            app_data_dir = os.path.abspath(get_app_data_dir())
            if not abs_file.startswith(app_data_dir):
                logger.error(f"Invalid auto-exclude file path during reload: {AUTO_EXCLUDE_FILE}")
                return False
            with open(AUTO_EXCLUDE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip().lower()
                    if line and not line.startswith("#") and line[0].isalnum():
                        if not line.endswith(".exe"):
                            line += ".exe"
                        new_set.add(line)
        except (OSError, IOError) as e:
            logger.warning(f"Failed to reload auto-exclude file: {e}")
            return False  # File read failed — keep existing exclusions

    # Swap atomically using module-level lock
    with _AUTO_EXCLUDED_LOCK:
        _AUTO_EXCLUDED_EXES = new_set

    return True  # Success


def _is_auto_excluded(exe_path):
    """Return True if this exe should be completely ignored by the tracker."""
    if exe_path:
        exe_name = os.path.basename(exe_path).lower()
        # Fast path: check set membership without lock (set lookups are thread-safe for reads)
        return exe_name in _AUTO_EXCLUDED_EXES
    return False


# Run on module load — order matters: generate first, then load
create_auto_excluded_if_missing()
_load_auto_excluded()

SETTINGS_FILE = os.path.join(get_app_data_dir(), "settings.json")
TAGS_FILE = os.path.join(get_app_data_dir(), "tags.json")


class TagManager:
    """Manages application project/category tags locally and thread-safely."""
    DEFAULT_PROJECTS = ["Development", "Design", "Research", "Documentation", "Communication", "Management", "Unassigned"]
    
    # Offline keyword lists
    KEYWORDS = {
        "Development": ["code", "studio", "compiler", "ide", "git", "docker", "sublime", "debugger", "terminal", "powershell", "python", "node", "npm", "cargo", "msbuild", "visual studio", "pycharm", "intellij", "vscode"],
        "Design": ["photoshop", "illustrator", "design", "draw", "cad", "paint", "premiere", "blend", "creative", "maya", "blender", "canvas", "figma", "sketch", "invision", "rendering", "image editor"],
        "Documentation": ["word", "excel", "pdf", "document", "notion", "obsidian", "writer", "spreadsheet", "powerpoint", "slides", "notes", "acrobat", "typora", "logseq"],
        "Communication": ["slack", "teams", "discord", "zoom", "outlook", "whatsapp", "messenger", "skype", "telegram", "thunderbird", "mail", "chat", "meeting"],
        "Research": ["chrome", "firefox", "edge", "safari", "browser", "google", "search", "wikipedia", "navigator", "opera", "brave"],
        "Management": ["project", "jira", "trello", "asana", "trello", "clickup", "monday.com", "board", "gantt", "backlog"]
    }
    
    def __init__(self):
        self.lock = threading.Lock()
        self.projects = list(self.DEFAULT_PROJECTS)
        self.mappings = {}
        self._load_tags()
        
    def _load_tags(self):
        if not os.path.exists(TAGS_FILE):
            self._save_tags()
            return
        try:
            with open(TAGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.projects = data.get("projects", list(self.DEFAULT_PROJECTS))
                # Ensure "Unassigned" is always present
                if "Unassigned" not in self.projects:
                    self.projects.append("Unassigned")
                self.mappings = data.get("mappings", {})
        except Exception as e:
            logger.warning(f"Failed to load tags config: {e}")
            self.projects = list(self.DEFAULT_PROJECTS)
            self.mappings = {}
            
    def _save_tags(self):
        try:
            dirpath = os.path.dirname(TAGS_FILE)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            temp_file = TAGS_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({
                    "projects": self.projects,
                    "mappings": self.mappings
                }, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, TAGS_FILE)
        except Exception as e:
            logger.warning(f"Failed to save tags config: {e}")
            
    def get_tag(self, app_name: str, exe_path: str = "") -> str:
        """Get tag for app. If not mapped, runs offline heuristics + asynchronous online fallback."""
        key = app_name.lower().strip()
        
        with self.lock:
            if key in self.mappings:
                return self.mappings[key]
                
        # If not mapped, perform offline matching
        matched_tag = self._match_offline(app_name, exe_path)
        if matched_tag:
            with self.lock:
                self.mappings[key] = matched_tag
                self._save_tags()
            return matched_tag
            
        # If offline fails, start a background online fetch
        # Set to "Unassigned" temporarily, then update asynchronously
        with self.lock:
            self.mappings[key] = "Unassigned"
            self._save_tags()
            
        # Start background thread to query DDG API
        threading.Thread(target=self._fetch_and_update_tag_online, args=(app_name, exe_path), daemon=True).start()
        return "Unassigned"
        
    def set_tag(self, app_name: str, tag: str):
        key = app_name.lower().strip()
        with self.lock:
            if tag in self.projects or tag == "Unassigned":
                self.mappings[key] = tag
                self._save_tags()
                
    def add_project(self, project: str) -> bool:
        project = project.strip()
        if not project:
            return False
        with self.lock:
            if project not in self.projects:
                self.projects.append(project)
                self._save_tags()
                return True
        return False
        
    def remove_project(self, project: str) -> bool:
        if project == "Unassigned":
            return False  # Protect Unassigned
        with self.lock:
            if project in self.projects:
                self.projects.remove(project)
                # Remap apps that were in this project to "Unassigned"
                for k, v in list(self.mappings.items()):
                    if v == project:
                        self.mappings[k] = "Unassigned"
                self._save_tags()
                return True
        return False

    def _match_offline(self, app_name: str, exe_path: str) -> Optional[str]:
        """Offline keyword heuristic matching."""
        # Clean terms to search
        search_terms = [app_name.lower()]
        if exe_path:
            exe_name = os.path.basename(exe_path).lower()
            if exe_name.endswith(".exe"):
                exe_name = exe_name[:-4]
            search_terms.append(exe_name)
            
            # Fetch FileDescription locally
            from appinfo import _get_file_description
            desc = _get_file_description(exe_path)
            if desc:
                search_terms.append(desc.lower())
                
        # Match search terms against keywords
        for category, words in self.KEYWORDS.items():
            for term in search_terms:
                for word in words:
                    if word in term:
                        return category
        return None

    def _fetch_and_update_tag_online(self, app_name: str, exe_path: str):
        """Asynchronously query DuckDuckGo and update mapping on success."""
        try:
            import urllib.request
            import urllib.parse
            
            # Use app name or file description for better search accuracy
            search_query = app_name
            if exe_path:
                from appinfo import _get_file_description
                desc = _get_file_description(exe_path)
                if desc and len(desc) > 3:
                    search_query = desc
                    
            url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(search_query)}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) TrueHour/1.0'})
            
            # Query DuckDuckGo API with a clean 3.0s timeout
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    abstract = data.get("AbstractText", "") or data.get("Abstract", "")
                    
                    if abstract:
                        abstract_lower = abstract.lower()
                        # Run our keyword matcher against the online description
                        matched_tag = None
                        for category, words in self.KEYWORDS.items():
                            for word in words:
                                if word in abstract_lower:
                                    matched_tag = category
                                    break
                            if matched_tag:
                                break
                                
                        if matched_tag:
                            key = app_name.lower().strip()
                            with self.lock:
                                self.mappings[key] = matched_tag
                                self._save_tags()
                            logger.info(f"Online categorization succeeded for '{app_name}' -> '{matched_tag}'")
        except Exception as e:
            logger.debug(f"Online categorization background query failed for {app_name}: {e}")




class SessionStorage:
    """Handles serialization and persistence of tracking sessions."""
    @staticmethod
    def save_state(tracker: 'AppTracker', filepath: str):
        try:
            with tracker._lock:
                state = {
                    "session_start": tracker.session_start.timestamp() if tracker.session_start else None,
                    "session_name": tracker.session_name,
                    "app_times": tracker.app_times.copy(),
                    "app_included": tracker.app_included.copy(),
                    "app_exe_paths": tracker.app_exe_paths.copy(),
                    "timeline": [
                        {"app": t["app"], "start": t["start"].timestamp(), "end": t["end"].timestamp()}
                        for t in tracker.timeline
                    ],
                    "paused": tracker.paused,
                    "_pause_start": tracker._pause_start,
                    "_total_paused_time": tracker._total_paused_time,
                    "_current_app": tracker._current_app,
                    "_current_start": tracker._current_start,
                    "_current_block_start": tracker._current_block_start,
                    "_current_block_active": tracker._current_block_active
                }
            
            # Atomic file swap
            temp_file = filepath + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state, f)
            os.replace(temp_file, filepath)
        except Exception as e:
            logger.warning(f"Failed to save active state: {e}")

class AppTracker:
    """Tracks which application is in the foreground and for how long."""

    def __init__(self, poll_interval=1.0, min_track_seconds=2):
        self.poll_interval = poll_interval
        self.min_track_seconds = min_track_seconds

        # Session state
        self.running = False
        self.paused = False
        self.session_start = None
        self.session_end = None
        self._pause_start = None
        self._total_paused_time = 0
        self._last_save_time = 0
        self.is_recovered = False
        self.session_name = ""
        self.save_interval = 10  # Default backup interval

        # {app_name: total_seconds}
        self.app_times = {}
        # {app_name: bool} — True = included
        self.app_included = {}
        # {app_name: exe_path} — for icon extraction
        self.app_exe_paths = {}
        # Timeline: list of {"app", "start", "end"}
        self.timeline = []

        # Current tracking
        self._current_app = None
        self._current_start = None
        self._current_block_start = None
        self._current_block_active = 0
        self._thread = None
        self._lock = threading.Lock()

        # Callbacks
        self.on_update = None  # called each poll tick

        # Persistent Exclusions
        self.persistent_excluded = set()
        self._load_settings()
        self.tag_manager = TagManager()
        
        # Idle auto-pause
        self.idle_threshold_seconds = 0  # 0 = disabled
        self._idle_paused = False

        # Security: Time tamper detection
        self.security_detector = None
        self.integrity_warnings = []

        # Resume tracking: snapshot of app_times at the moment a past session was resumed.
        # None = fresh start or crash recovery. dict = resumed from Session Manager.
        self.resume_snapshot = None

    def _load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                # Validate file path to prevent path traversal
                abs_file = os.path.abspath(SETTINGS_FILE)
                app_data_dir = os.path.abspath(get_app_data_dir())
                if not abs_file.startswith(app_data_dir):
                    logger.error(f"Invalid settings file path: {SETTINGS_FILE}")
                    return
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.persistent_excluded = set(data.get("excluded_apps", []))
            except (OSError, IOError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load settings: {e}")

    def _save_settings(self):
        try:
            dirpath = os.path.dirname(SETTINGS_FILE)
            if dirpath:
                # Validate directory path to prevent path traversal
                abs_dir = os.path.abspath(dirpath)
                app_data_dir = os.path.abspath(get_app_data_dir())
                if not abs_dir.startswith(app_data_dir):
                    logger.error(f"Invalid settings directory path: {dirpath}")
                    return
                os.makedirs(dirpath, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"excluded_apps": list(self.persistent_excluded)}, f, indent=2)
        except (OSError, IOError) as e:
            logger.warning(f"Failed to save settings: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, session_name=""):
        """Begin a tracking session."""
        if self.running:
            return
        
        # Initialize security detector for this session
        reset_detector()
        self.security_detector = get_detector()
        self.security_detector.start_session()
        
        self.running = True
        self.paused = False
        self.session_start = datetime.now()
        self.session_end = None
        self._pause_start = None
        self._total_paused_time = 0
        self._last_save_time = time.time()
        self.is_recovered = False
        self.session_name = session_name
        self.app_times.clear()
        self.app_included.clear()
        self.app_exe_paths.clear()
        self.timeline.clear()
        self._current_app = None
        self._current_start = None
        self._current_block_start = None
        self._current_block_active = 0
        self.integrity_warnings.clear()
        self.resume_snapshot = None  # Fresh start — no previous session
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """End the tracking session and finalize data."""
        if not self.running:
            return
        self.running = False
        self.session_end = datetime.now()
        # Flush current app
        self._flush_current()
        if self.paused and self._pause_start:
            self._total_paused_time += (time.time() - self._pause_start)
            self._pause_start = None
            
        if self._thread:
            self._thread.join(timeout=0.1)  # Non-blocking: thread exits via running flag
            self._thread = None
            
        # Finalize security detector
        if self.security_detector:
            security_report = self.security_detector.end_session()
            if security_report["trust_score"] < 70:
                self.integrity_warnings.append({
                    "type": "LOW_TRUST_SCORE",
                    "score": security_report["trust_score"],
                    "events_count": security_report.get("tamper_events_count", len(security_report.get("tamper_events", [])))
                })
        
        if os.path.exists(ACTIVE_SESSION_FILE):
            try:
                # Validate file path before deletion
                abs_file = os.path.abspath(ACTIVE_SESSION_FILE)
                app_data_dir = os.path.abspath(get_app_data_dir())
                if not abs_file.startswith(app_data_dir):
                    logger.error(f"Invalid active session file path: {ACTIVE_SESSION_FILE}")
                else:
                    os.remove(ACTIVE_SESSION_FILE)
            except OSError as e:
                logger.warning(f"Failed to remove active session file: {e}")
    
    def get_security_status(self):
        """Return current security/integrity status of the session."""
        if not self.security_detector:
            return {"status": "NOT_STARTED", "trust_level": "UNKNOWN"}
        
        report = self.security_detector.get_session_report()
        return {
            "status": "ACTIVE" if self.running else "ENDED",
            "trust_score": report["trust_score"],
            "trust_level": report["trust_level"],
            "chain_valid": report["chain_valid"],
            "tamper_events": report["tamper_events_count"],
            "warnings": self.integrity_warnings
        }

    def recover_session(self):
        if not os.path.exists(ACTIVE_SESSION_FILE):
            return False
        try:
            # Validate file path to prevent path traversal
            abs_file = os.path.abspath(ACTIVE_SESSION_FILE)
            app_data_dir = os.path.abspath(get_app_data_dir())
            if not abs_file.startswith(app_data_dir):
                logger.error(f"Invalid active session file path: {ACTIVE_SESSION_FILE}")
                return False
            with open(ACTIVE_SESSION_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                
            self.session_start = datetime.fromtimestamp(state["session_start"])
            self.app_times = state["app_times"]
            self.app_included = state.get("app_included", {})
            self.app_exe_paths = state.get("app_exe_paths", {})
            self.timeline = []
            for t in state["timeline"]:
                self.timeline.append({
                    "app": t["app"],
                    "start": datetime.fromtimestamp(t["start"]),
                    "end": datetime.fromtimestamp(t["end"])
                })
            self.paused = state.get("paused", False)
            self._pause_start = state.get("_pause_start")
            self._total_paused_time = state.get("_total_paused_time", 0)
            
            c_app = state.get("_current_app")
            c_start = state.get("_current_start")
            c_block_start = state.get("_current_block_start")
            c_block_active = state.get("_current_block_active", 0)
            
            if c_app and c_block_start:
                crash_time = os.path.getmtime(ACTIVE_SESSION_FILE)
                if c_start:
                    elapsed = crash_time - c_start
                    if elapsed > 0:
                        if elapsed > self.poll_interval + 2.0:
                            elapsed = self.poll_interval
                        if self.app_included.get(c_app, True):
                            self.app_times[c_app] = self.app_times.get(c_app, 0) + elapsed
                            c_block_active += elapsed

                if c_block_active >= self.min_track_seconds:
                    self.timeline.append({
                        "app": c_app,
                        "start": datetime.fromtimestamp(c_block_start),
                        "end": datetime.fromtimestamp(c_block_start + c_block_active)
                    })
            
            self._current_app = None
            self._current_start = None
            self.running = True
            self.session_end = None
            self.is_recovered = True
            
            # Adjust paused time to account for the gap while the app was closed
            now = datetime.now()
            tracked_duration = sum(self.app_times.values())
            self._total_paused_time = max(0, (now - self.session_start).total_seconds() - tracked_duration)
            if self.paused:
                self._pause_start = time.time()  # reset so UI shows correct paused state
            
            self.resume_snapshot = None  # Crash recovery — not a user-initiated resume
            self._last_save_time = time.time()
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            return True
        except (OSError, IOError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to recover session: {e}")
            return False

    def load_from_report(self, filepath):
        from report import load_session_json
        try:
            rep = load_session_json(filepath)
            
            self.session_name = rep.get("session_name", "")
            
            self.session_start = datetime.strptime(rep['date'] + " " + rep['start'], "%Y-%m-%d %H:%M:%S")
            self.session_end = None
            
            self.app_exe_paths = rep.get("app_exe_paths", {})

            # Load app_times but strip any auto-excluded apps from old sessions
            self.app_times = {}
            self.app_included = {}

            for a in rep['apps']:
                name = a['name']
                secs = a['seconds']
                included = not a['excluded']
                exe_path = self.app_exe_paths.get(name, "")
                
                if not _is_auto_excluded(exe_path) and name != "[Idle]":
                    self.app_times[name] = secs
                    self.app_included[name] = included
                
            self.timeline.clear()
            for t in rep['timeline']:
                # load_session_json returns datetime objects; handle both formats
                if isinstance(t['start'], datetime):
                    t_start = t['start']
                    t_end = t['end']
                else:
                    t_start = datetime.strptime(rep['date'] + " " + t['start'], "%Y-%m-%d %H:%M:%S")
                    t_end = datetime.strptime(rep['date'] + " " + t['end'], "%Y-%m-%d %H:%M:%S")
                
                # Midnight crossover guard
                if t_end <= t_start:
                    t_end += timedelta(days=1)
                    
                self.timeline.append({
                    "app": t['app'],
                    "start": t_start,
                    "end": t_end
                })
                
            self._current_app = None
            self._current_start = None
            self._current_block_start = None
            self._current_block_active = 0
            self.integrity_warnings = []
            
            # Initialize security detector for resumed session
            reset_detector()
            self.security_detector = get_detector()
            self.security_detector.start_session()
            
            # Important: Adjust paused time so the timer respects the saved duration
            # (Now - Start) - Paused = Saved_Duration
            now = datetime.now()
            self._total_paused_time = (now - self.session_start).total_seconds() - rep['total_seconds']
            
            self.paused = False
            self._pause_start = None
            self.running = True
            self.is_recovered = False
            # Snapshot current app_times BEFORE the poll thread starts adding new time.
            # Anything beyond these values at stop time = new activity from this resume.
            self.resume_snapshot = dict(self.app_times)
            self._last_save_time = time.time()
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            return True
        except (OSError, IOError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to load from report: {e}")
            return False

    def load_crash_data(self):
        """Loads crash data into the tracker instance without starting the thread."""
        if not os.path.exists(ACTIVE_SESSION_FILE):
            return False
        try:
            with open(ACTIVE_SESSION_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.session_start = datetime.fromtimestamp(state["session_start"])
            self.session_name = state.get("session_name", "")
            self.app_times = state["app_times"]
            self.app_included = state.get("app_included", {})
            self.app_exe_paths = state.get("app_exe_paths", {})
            self.timeline = []
            for t in state["timeline"]:
                self.timeline.append({
                    "app": t["app"],
                    "start": datetime.fromtimestamp(t["start"]),
                    "end": datetime.fromtimestamp(t["end"])
                })
            
            # Restore pause data
            self.paused = state.get("paused", False)
            self._pause_start = time.time() if self.paused else None
            self._total_paused_time = state.get("_total_paused_time", 0)
            
            # Flush any current app active during the crash
            c_app = state.get("_current_app")
            c_start = state.get("_current_start")
            c_block_start = state.get("_current_block_start")
            c_block_active = state.get("_current_block_active", 0)
            if c_app and c_block_start:
                crash_time = os.path.getmtime(ACTIVE_SESSION_FILE)
                if c_start:
                    elapsed = crash_time - c_start
                    if elapsed > 0:
                        if elapsed > self.poll_interval + 2.0:
                            elapsed = self.poll_interval
                        if self.app_included.get(c_app, True):
                            self.app_times[c_app] = self.app_times.get(c_app, 0) + elapsed
                            c_block_active += elapsed
                
                if c_block_active >= self.min_track_seconds:
                    self.timeline.append({
                        "app": c_app,
                        "start": datetime.fromtimestamp(c_block_start),
                        "end": datetime.fromtimestamp(c_block_start + c_block_active)
                    })
            
            self.session_end = datetime.fromtimestamp(os.path.getmtime(ACTIVE_SESSION_FILE))
            self.is_recovered = True
            
            # Initialize security detector for recovered session
            self.security_detector = get_detector()
            return True
        except Exception:
            return False

    def toggle_pause(self):
        with self._lock:
            if not self.running:
                return False
            self.paused = not self.paused
            now = time.time()
            if self.paused:
                self._flush_current_unlocked(now)
                self._current_app = None
                self._current_start = None
                self._pause_start = now
            else:
                if self._pause_start:
                    self._total_paused_time += (now - self._pause_start)
                    self._pause_start = None
            return self.paused

    def set_included(self, app_name, included):
        with self._lock:
            self.app_included[app_name] = included
            if not included:
                self.persistent_excluded.add(app_name)
            else:
                self.persistent_excluded.discard(app_name)
            self._save_settings()

    def get_included(self, app_name):
        with self._lock:
            return self.app_included.get(app_name, True)

    def get_app_times_sorted(self):
        # Fast path: avoid lock if no apps tracked yet
        if not self.app_times:
            return []
        
        with self._lock:
            return [
                (name, secs, self.app_included.get(name, True))
                for name, secs in sorted(
                    self.app_times.items(), key=lambda x: x[1], reverse=True
                )
                if not _is_auto_excluded(
                    self.app_exe_paths.get(name, "")
                )
                and name != "[Idle]"
            ]

    def get_counted_seconds(self):
        # Fast path: avoid lock if no apps tracked yet
        if not self.app_times:
            return 0
        with self._lock:
            return sum(
                s for a, s in self.app_times.items()
                if self.app_included.get(a, True)
                and not _is_auto_excluded(self.app_exe_paths.get(a, ""))
            )

    def get_total_seconds(self):
        # Fast path: avoid lock if no apps tracked yet
        if not self.app_times:
            return 0
        with self._lock:
            return sum(
                s for a, s in self.app_times.items()
                if not _is_auto_excluded(self.app_exe_paths.get(a, ""))
            )

    def get_elapsed(self):
        """Seconds since session started."""
        if self.session_start is None:
            return 0
        end = self.session_end or datetime.now()
        elapsed = (end - self.session_start).total_seconds()
        paused_time = self._total_paused_time
        if self.paused and self._pause_start:
            paused_time += (time.time() - self._pause_start)
        return max(0, elapsed - paused_time)

    def get_current_app(self):
        # Fast path for common case (not paused)
        if self.paused:
            with self._lock:
                return "Paused"
        return self._current_app or ""

    def get_exe_path(self, app_name):
        # Thread-safe read without explicit lock (dict get is atomic in CPython)
        return self.app_exe_paths.get(app_name, "")

    def get_app_tag(self, app_name: str) -> str:
        exe_path = self.get_exe_path(app_name)
        return self.tag_manager.get_tag(app_name, exe_path)

    def set_app_tag(self, app_name: str, tag: str):
        self.tag_manager.set_tag(app_name, tag)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _flush_current_unlocked(self, now):
        """Flush current app time. Must be called while holding self._lock."""
        if self._current_app and self._current_block_start:

            # Partial time since last per-tick update
            if self._current_start:
                partial = now - self._current_start

                if partial > 0:

                    # Guard against OS sleep leaps
                    if partial > self.poll_interval + 2.0:

                        self._total_paused_time += (
                            partial - self.poll_interval
                        )

                        if self.app_included.get(self._current_app, True):
                            self.app_times[self._current_app] = (
                                self.app_times.get(self._current_app, 0)
                                + self.poll_interval
                            )
                            self._current_block_active += self.poll_interval

                    else:

                        if self.app_included.get(self._current_app, True):
                            self.app_times[self._current_app] = (
                                self.app_times.get(self._current_app, 0)
                                + partial
                            )
                            self._current_block_active += partial

            if self._current_block_active >= self.min_track_seconds:

                self.timeline.append({
                    "app": self._current_app,
                    "start": datetime.fromtimestamp(self._current_block_start),
                    "end": datetime.fromtimestamp(self._current_block_start + self._current_block_active),
                })

            self._current_start = None
            self._current_block_start = None
            self._current_block_active = 0

    def _flush_current(self):
        with self._lock:
            self._flush_current_unlocked(time.time())

    def _poll_loop(self):
        """Main tracking loop - optimized to reduce callback overhead."""
        last_callback_time = 0
        callback_interval = 0.5  # Only trigger UI update every 500ms max
        
        while self.running:
            # ── Idle auto-pause check ────────────────────────────────
            if self.idle_threshold_seconds > 0:
                idle_secs = _get_idle_seconds()
                if not self.paused and idle_secs >= self.idle_threshold_seconds:
                    # User went idle — auto-pause
                    self._idle_paused = True
                    self.toggle_pause()
                    if self.on_update:
                        try: self.on_update()
                        except: pass
                elif self._idle_paused and idle_secs < self.idle_threshold_seconds:
                    # Activity resumed — auto-resume
                    self._idle_paused = False
                    if self.paused:
                        self.toggle_pause()
                    if self.on_update:
                        try: self.on_update()
                        except: pass
            if self.paused:
                time.sleep(self.poll_interval)
                continue

            app, exe_path = get_foreground_app_info()
            now = time.time()

            should_callback = (now - last_callback_time) >= callback_interval
            
            with self._lock:
                # Completely skip auto-excluded apps — do not record, do not store.
                # Instead, we "pretend" the last real app is still focused.
                # This ensures time keeps accumulating on the real app and the UI stays alive.
                if _is_auto_excluded(exe_path):
                    app = self._current_app

                if app != self._current_app:
                    self._flush_current_unlocked(now)
                    self._current_app = app
                    self._current_start = now
                    self._current_block_start = now

                    if app and exe_path:
                        self.app_exe_paths[app] = exe_path

                    if app and app not in self.app_included:
                        if app in self.persistent_excluded:
                            self.app_included[app] = False
                        else:
                            self.app_included[app] = (app != "[Idle]")
                    
                    # Always callback on app switch for immediate UI response
                    should_callback = True
                else:
                    if self._current_app and self._current_start:
                        elapsed = now - self._current_start

                        # Guard against OS sleep/suspend massive time leaps
                        if elapsed > self.poll_interval + 2.0:
                            self._total_paused_time += (elapsed - self.poll_interval)
                            elapsed = self.poll_interval

                        if self.app_included.get(self._current_app, True):
                            self.app_times[self._current_app] = (
                                self.app_times.get(self._current_app, 0) + elapsed
                            )
                            self._current_block_active += elapsed
                        self._current_start = now
                        
                        # Security: Validate and record with tamper detection
                        if self.security_detector and self._current_app and self.app_included.get(self._current_app, True):
                            validation = self.security_detector.validate_and_record(
                                self._current_app, 
                                elapsed
                            )
                            
                            # Log integrity issues
                            if validation["integrity_status"] == "TAMPER_DETECTED":
                                warning = {
                                    "type": "TIME_TAMPER_DETECTED",
                                    "app": self._current_app,
                                    "discrepancy": validation["discrepancy"],
                                    "timestamp": datetime.now().isoformat()
                                }
                                self.integrity_warnings.append(warning)
                            elif validation["integrity_status"] == "SUSPICIOUS":
                                warning = {
                                    "type": "SUSPICIOUS_TIME_CHANGE",
                                    "app": self._current_app,
                                    "discrepancy": validation["discrepancy"],
                                    "timestamp": datetime.now().isoformat()
                                }
                                self.integrity_warnings.append(warning)

            # Throttled callback to reduce UI update frequency
            if should_callback and self.on_update:
                try:
                    self.on_update()
                    last_callback_time = now
                except Exception:
                    pass

            if now - self._last_save_time > self.save_interval:
                self._save_active_state()
                self._last_save_time = now

            time.sleep(self.poll_interval)

    def _save_active_state(self):
        SessionStorage.save_state(self, ACTIVE_SESSION_FILE) 
