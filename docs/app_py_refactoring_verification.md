# TrueHour `app.py` Refactoring — Verification & Audit Document

> **Purpose**: Complete structural audit of `app.py` (3,788 lines, 154 KB) for an independent agent to verify the proposed refactoring implementation plan. It maps every class, method, signal/slot connection, cross-module dependency, and inline dialog to ensure zero-breakage during modularization.

> **Revision 2** — every line reference below was re-verified against the working tree on branch `v4-beta.3`. Corrections from the first revision are marked ⚠️ **CORRECTED**. See §13 for the verification method and baseline.

---

## 0. Verified Baseline (Pre-Refactor)

Established before any change, so regressions are attributable:

| Check | Command | Result |
|---|---|---|
| Syntax | `python -m py_compile app.py` | ✅ OK |
| Module imports | 25 project modules imported individually | ✅ 0 failures |
| Test suite | `python -m pytest tests/ -q` | ✅ **94 passed** in 7.00s |
| Method census (AST) | `TrueHourApp` function defs | **60 defs / 59 unique** |
| Line count | `wc -l app.py` | **3,788** |

⚠️ **CORRECTED**: The file is **3,788** lines, not 3,789. All downstream percentage math in this document uses 3,788.

Re-run all four checks after each extraction step. The AST census is the cheapest regression detector — it must stay at 59 unique names minus whatever you intentionally remove.

---

## 1. Current Project Structure (Already Modularized)

The project has **already extracted** several components. The plan must not duplicate or conflict with these:

```
TrueHour/
├── app.py                      # 3,788 lines — THE TARGET
├── tracker.py                  # AppTracker, session state, poll loop
├── config.py                   # get_app_data_dir, DynamicPath, open_file
├── report.py                   # format_duration, build_report_data, export, HTML gen
├── theme.py                    # QSS generation, palettes, SVG icon helpers, tag colors
├── crypto.py                   # _get_secure_key, _encrypt_string, _decrypt_string
├── assets.py                   # SVG string constants (GITHUB_SVG, SUN_SVG, etc.)
├── version.py                  # VERSION_FULL, INFO, __version__
├── appinfo.py                  # App name resolution and overrides
├── secure_time.py              # Time manipulation detection
├── debug_terminal.py           # LogBufferCollector, DebugTerminalWindow
├── drive_sync.py               # Google Drive sync utilities
├── dashboard_widgets.py        # Dashboard chart/widget helpers
│
├── dialogs/                    # ✅ ALREADY EXTRACTED
│   ├── __init__.py
│   ├── dashboard_dialog.py     # TrueHourDashboard (37 KB)
│   ├── session_manager.py      # SessionManagerDialog (66 KB)
│   └── settings_dialog.py      # SettingsDialog (72 KB)
│
├── widgets/                    # ✅ ALREADY EXTRACTED
│   ├── __init__.py
│   ├── custom_widgets.py       # SegmentedAllocationBar, AppUsageRow (31 KB)
│   ├── loading_dialog.py       # LoadingDialog (5 KB)
│   └── update_label.py         # FadingVersionLabel (8 KB)
│
├── workers/                    # ✅ ALREADY EXTRACTED — note: no __init__.py (namespace pkg)
│   ├── drive_sync_worker.py    # DriveSyncWorker
│   └── report_worker.py        # ReportWorker
│
├── core/                       # ✅ ALREADY EXISTS
│   ├── backup_manager.py
│   ├── update_checker.py       # UpdateCheckSignals, check_for_updates_async
│   └── reporting/
│       ├── aggregator.py       # rebuild_all_summaries
│       └── web_server.py       # WebServerManager
│
├── database/
│   └── schema.py               # init_db, optimize_db
│
└── templates/
    ├── goals_dashboard.html
    └── about_legal.html
```

> [!IMPORTANT]
> The original implementation plan proposed creating `ui/dialogs/settings_dialog.py`, `ui/dialogs/session_manager.py`, and `core/workers.py`. **These already exist** as `dialogs/settings_dialog.py`, `dialogs/session_manager.py`, and `workers/report_worker.py`. The plan must be corrected to avoid duplicating already-extracted modules.

> [!NOTE]
> **`utils/` does not exist.** Verified — it is a genuinely new package. `workers/` has no `__init__.py` and works as an implicit namespace package, so one is not strictly required for `utils/`, but add it for consistency with `dialogs/` and `widgets/`.

### Reverse-Dependency Check (New)

```
grep -rn "from app import\|^import app" --include=*.py .   →  0 hits
```

**Nothing in the codebase imports `app`.** This is the single most important safety fact in this document: extracting `HeaderBar`, `pil_to_pixmap`, or `get_native_icon_pixmap` into new modules carries **zero circular-import risk**, because no existing module can create a cycle back through `app.py`.

---

## 2. Complete Class & Function Inventory in `app.py`

### Top-Level Functions (Lines 1–178)

| Function | Lines | Description | Dependencies |
|---|---|---|---|
| `pil_to_pixmap(pil_img)` | 86–98 | Converts PIL Image → QPixmap via PNG bytes | `io`, `QImage`, `QPixmap`, `logger` |
| `get_native_icon_pixmap(exe_path, size)` | 108–122 | Extracts native Windows file icon | `QFileIconProvider`, `QFileInfo`, `QSize`, `os`, global `_ICON_PROVIDER` |
| `handle_exception(exc_type, exc_value, exc_traceback)` | 154–161 | Global uncaught exception hook | `logger`, `sys.__excepthook__` |
| `_force_light_mode()` | 168–174 | Forces Windows light theme via `ctypes.windll.uxtheme` | `ctypes` |

> [!CAUTION]
> **`pil_to_pixmap` uses `logger`, which is not defined until line 130.** The function body only runs at call time so this works today, but if it moves to `utils/icon_utils.py` that module must create its own logger (`logging.getLogger(__name__)`) rather than inheriting `app`'s. The same applies to `get_native_icon_pixmap` (line 120). Do not import `logger` from `app` — that would create the circular dependency §1 confirms does not currently exist.

### Module-Level Side Effects (Execute on Import)

| Line(s) | Side Effect | Risk if Moved |
|---|---|---|
| 101 | `from crypto import ...` — mid-file import, **not** in the top import block | Cosmetic; safe to hoist |
| 105 | `_ICON_PROVIDER = None` global | Must remain accessible to `get_native_icon_pixmap` |
| 125–127 | `log_collector = LogBufferCollector()` + `start_redirection()` | Captures stdout/stderr early. Must execute before any print/log |
| 129–148 | Logger setup with stream + file handler | Must execute before any `logger.debug/info/etc` call |
| 164 | `sys.excepthook = handle_exception` | Must execute before QApplication creation |
| 177 | `_force_light_mode()` call | Must execute before QApplication creation |

> [!WARNING]
> These module-level side effects run immediately on `import app`. Any refactoring that moves them to a different module must ensure they still execute **before** `QApplication` is created and before any logging occurs. If `app.py` becomes a thin launcher that imports `ui.main_window`, these side effects must either stay in `app.py` or be explicitly called at the top of the launcher.

### Classes

#### `TrackerSignals(QObject)` — Line 181

```python
class TrackerSignals(QObject):
    update_signal = pyqtSignal()
```

- **Used by**: `TrueHourApp.__init__` (lines 323–324): `self.signals = TrackerSignals()`, connected to `self._schedule_refresh`
- **Also connected**: `self.tracker.on_update = lambda: self.signals.update_signal.emit()` (line 371)
- **Purpose**: Thread-safe bridge from background `AppTracker` polling thread → main GUI thread refresh

#### `HeaderBar(QFrame)` — Lines 188–280

- **Constructor args**: `parent, cmd_report, cmd_sessions, cmd_settings, cmd_toggle_theme`
- **Widgets created**: `theme_btn`, `live_report_btn` (labelled "Dashboard"), `sessions_btn`, `settings_btn`
- **Signal connections made by caller** (lines 593–599):
  - `cmd_report` → `self._show_dashboard`
  - `cmd_sessions` → `self._show_session_manager`
  - `cmd_settings` → `self._show_settings`
  - `cmd_toggle_theme` → `self._toggle_theme`
- **Public method**: `update_theme(theme_style=None, is_dark=None)` — called from its own `__init__` (line 233, with `"light"`) and from `TrueHourApp.apply_theme()` (line 2098)
- **Inline QSS**: Lines 268–280 (`live_report_btn` stylesheet)
- **Dependencies**: `get_svg_icon`, `create_minimalist_icon`, `SUN_SVG`, `SOLID_MOON_SVG` (from `theme.py` and `assets.py`)

> [!NOTE]
> `live_report_btn` is wired to `cmd_report` → `_show_dashboard`, **not** to `_show_live_report`. The naming is misleading but the behaviour is correct. Do not "fix" this during extraction.

#### `TrueHourApp(QMainWindow)` — Lines 290–3703

This is the monolith. Below is a complete method inventory — **60 definitions, 59 unique names** (AST-verified).

---

## 3. Complete `TrueHourApp` Method Inventory

### Initialization & Lifecycle

| Method | Lines | Category | Blocking? |
|---|---|---|---|
| `__init__` | 291–455 | Init: tracker, settings, tray, UI, timers, deferred tasks | Partially (DB init, settings load) |
| `closeEvent` (first def) | 457–461 | Drive sync worker cleanup on close — **DEAD CODE** | No |
| `closeEvent` (second def, overrides) | 795–835 | Full shutdown: confirm dialog, stop tracker, autosave, cleanup | Yes (report build, file I/O) |
| `run` | 3702–3703 | `self.show()` | No |

> [!CAUTION]
> **Confirmed by AST**: `TrueHourApp` has 60 method definitions but only 59 unique names. The sole duplicate is `closeEvent` (lines 457 and 795). The second definition wins at class-construction time, so the drive-sync cleanup at 457–461 **never executes**. This is a real bug, not a documentation artifact. **Fix it before or during refactoring** — see §6.

### Deferred Startup Tasks (All via `QTimer.singleShot` in `__init__`)

| Delay | Task | Line |
|---|---|---|
| 100ms | `_handle_interrupted_session` (only if `ACTIVE_SESSION_FILE` exists) | 379 |
| 2500ms | `rebuild_all_summaries` (background thread) | 392–394 |
| 3000ms | `optimize_db` (background thread) | 437–438 |
| 3500ms | `_recalculate_weekly_base_focus_seconds` | 395 |
| 4000ms | `_deferred_start_web_server` (WebServerManager) | 424 |
| 5000ms | `check_for_updates_async` | 450–451 |
| 6000ms | `_trigger_deferred_drive_sync` | 455 |

> [!IMPORTANT]
> `_deferred_start_web_server` is **a local closure defined at line 399 inside `__init__`**, not a method on the class. It is absent from the AST method census for that reason. All five `web_server_mgr` signal connections (§4) live inside this closure. Any extraction of `__init__` must carry the closure and its five connections together.

### UI Construction

| Method | Lines | Notes |
|---|---|---|
| `_build_ui` | 585–793 | Builds: HeaderBar, clock card, app list scroll area, footer, version bar, debug buttons |
| `_center_window` | 578–583 | Utility for centering any window — **shared by 3 inline dialogs**, see §10 |

### Session Control (Start/Stop/Pause)

| Method | Lines | Notes |
|---|---|---|
| `_on_start` | 837–874 | Starts tracker, clears UI, enables buttons, starts clock timer |
| `_on_stop` | 876–952 | Stops timer, updates UI, spawns `ReportWorker` + `LoadingDialog`, then calls `_show_compact_save_dialog` (line 930) |
| `_update_pause_btn_ui` | 954–967 | Updates pause/resume icon and text |
| `_on_pause` | 969–992 | Toggles pause, updates button styles, tray text |

### Live Report ⚠️ **CORRECTED — was missing entirely**

| Method | Lines | Notes |
|---|---|---|
| `_show_live_report` | 994–1025 (32 lines) | Guards on `tracker.running`, spawns `ReportWorker` + `LoadingDialog`, then calls `self._show_report(..., is_new=False, is_live=True)` at line 1013 |

> [!CAUTION]
> **This method was omitted from Revision 1 and it is the crux of the highest-value extraction.** `_show_live_report` calls `_show_report`, and `_show_report` calls back into `_show_live_report` at line 2760:
> ```python
> ref_btn.clicked.connect(lambda: (dialog.accept(), self._show_live_report()))
> ```
> This is a **re-entrant cycle**: the report dialog's "Refresh" button closes the dialog and re-enters the owner, which rebuilds the report and re-opens the dialog. Extracting `_show_report` to `dialogs/report_dialog.py` therefore requires a re-open callback threaded back into `TrueHourApp`. See §10.

### Clock & Real-Time Updates

| Method | Lines | Notes |
|---|---|---|
| `_tick_clock` | 1027–1073 | Every 250ms: updates clock label, earnings, active app label, window title, checks goal milestones |
| `_schedule_refresh` | 1372–1379 | Rate-limited (0.5s) bridge from `TrackerSignals.update_signal` → `_refresh_app_list` |
| `_refresh_app_list` | 1381–1501 | Full app list rebuild: hash-based diffing, widget reuse, deferred icon loading |
| `_process_icon_load_queue` | 1503–1520 | Processes one icon per 30ms tick from `_icons_to_load` queue |
| `_clear_list_layout` | 1522–1533 | Removes all widgets from scroll layout |

### Goals & Earnings System

| Method | Lines | Notes |
|---|---|---|
| `_recalculate_weekly_base_focus_seconds` | 1098–1139 | Aggregates historical focus data excluding current session |
| `_check_weekly_goal_milestones` | 1141–1271 | Checks 50%/100% milestones, fires tray notifications |
| `_get_web_goals_state` | 1273–1311 | Builds state dict for web dashboard API |
| `_on_web_goals_reset` | 1313–1334 | Handles reset from web dashboard |
| `_on_web_goals_updated` | 1336–1360 | Handles goal updates from web dashboard |
| `_on_web_alerts_toggled` | 1362–1365 | Toggle notifications from web dashboard |
| `_on_web_theme_toggled` | 1367–1370 | Toggle dark mode from web dashboard |

### App List Interaction

| Method | Lines | Notes |
|---|---|---|
| `_toggle_include` | 1535–1537 | Include/exclude app from tracking |
| `_show_app_context_menu` | 1539–1555 | Right-click context menu for distraction marking |
| `_add_distraction_app` | 1557–1562 | Add app to distraction list |
| `_remove_distraction_app` | 1564–1570 | Remove app from distraction list |
| `_show_tag_menu` | 1572–1588 | Category/tag assignment popup menu |
| `_set_app_tag_and_refresh` | 1590–1594 | Apply tag and force refresh |

### Session Management

| Method | Lines | Notes |
|---|---|---|
| `_show_session_manager` | 1596–1646 | Opens `SessionManagerDialog`; its `_on_view_report_sm` closure calls `self._show_report(rep, is_new=False)` at line 1641 |
| `_resume_session` | 1648–1707 | Resumes a saved session from file |
| `_handle_interrupted_session` | 1709–1781 | Crash recovery dialog |

### Settings Persistence

| Method | Lines | Notes |
|---|---|---|
| `_load_app_settings` | 1783–1953 | Loads 45+ settings fields from JSON, handles legacy migration, encryption |
| `_save_app_settings` | 1955–2017 | Serializes all settings to JSON with encryption for bank details |

### Telemetry

| Method | Lines | Notes |
|---|---|---|
| `_init_posthog` | 2019–2055 | Initializes PostHog client (with embedded fallback API key for frozen builds) |
| `_track_event` | 2057–2072 | Captures and flushes a PostHog event |

> [!WARNING]
> `_init_posthog` contains a hardcoded PostHog API key at **line 2044**, gated behind `is_frozen` (line 2032) **and** `telemetry_config.TELEMETRY_ENABLED` (lines 2037–2039, wrapped in `try/except ImportError`). If this method is moved to a separate module, the `telemetry_config` soft-import must move with it or the gate silently defaults to `True`.

### Theming

| Method | Lines | Notes |
|---|---|---|
| `apply_theme` | 2074–2164 | Sets QSS, palette, updates header, clock, debug buttons, version label, refreshes app list. **Accepts `bool` or `str`** — coerces via `isinstance(theme_style, bool)` at line 2075 |
| `_toggle_theme` | 2166–2175 | Cycles light → modern-dark → classic-dark → light |

> [!NOTE]
> `__init__` calls `self.apply_theme(self.dark_mode)` (line 374) — passing a **bool**. `handle_rejected` (line 2359) passes `self.theme_style` — a **str**. Both paths are live. Preserve the dual-type coercion; do not tighten the signature during refactoring.

### Inline Dialogs (NOT yet extracted — still built imperatively in `app.py`)

| Method | Lines | Size | Dialog Type |
|---|---|---|---|
| `_show_bug_report_menu` | 2177–2205 | 29 lines | `QMessageBox` with custom buttons |
| `_show_settings` | 2207–2364 | **158 lines** | `SettingsDialog` wiring + 13 signal connections + 2 local closures |
| `_show_about_dialog` | 2366–2536 | 171 lines | `QDialog` (About window) |
| `_show_categories_dialog` | 2538–2674 | 137 lines | `QDialog` (Category manager) |
| `_show_report` | 2676–3148 | 473 lines | `QDialog` (Session report viewer) |
| `_show_compact_save_dialog` | 3150–3396 | 247 lines | `QDialog` (Post-session save prompt) |

⚠️ **CORRECTED**: `_show_settings` (158 lines) was omitted from Revision 1's inventory despite §4 listing 13 signal connections that live inside it. It is included here.

> [!IMPORTANT]
> The four extractable inline `QDialog` builders (`_show_about_dialog`, `_show_categories_dialog`, `_show_report`, `_show_compact_save_dialog`) total **1,028 lines** — 27% of `app.py`. `_show_settings` is *dialog wiring*, not a dialog body; it stays in `TrueHourApp` because it binds 13 owner methods. `_show_bug_report_menu` is a 29-line `QMessageBox` and is not worth a module.

### Export & Dashboard

| Method | Lines | Notes |
|---|---|---|
| `_export` | 3398–3445 | Export report to .txt or .html. **Sole call site is line 3108, inside `_show_report`** |
| `_show_dashboard` | 3447–3451 | Opens `TrueHourDashboard` from `dialogs/dashboard_dialog.py` |

### Profile Management

| Method | Lines | Notes |
|---|---|---|
| `_reload_active_profile` | 3453–3534 | Full profile reload: settings, DB, tracker, theme |
| `_handle_profile_switched` | 3536–3545 | Guards against switching during active session |
| `_handle_profile_renamed` | 3547–3608 | Renames profile directory with retry loop for Windows locks |
| `_handle_profile_deleted` | 3610–3694 | Deletes profile directory with aggressive cleanup |
| `_handle_settings_imported` | 3696–3700 | Reloads after settings import |

### Miscellaneous

| Method | Lines | Notes |
|---|---|---|
| `_trigger_deferred_drive_sync` | 463–485 | Background Google Drive sync |
| `_toggle_debug_console` | 487–498 | Launches debug console as subprocess (frozen check at line 493) |
| `_update_developer_ui` | 500–502 | Shows/hides debug and test buttons |
| `_on_update_found` | 504–510 | Handles update checker notification |
| `_on_version_clicked` | 512–562 | Easter egg: 7 clicks enables developer mode |
| `_trigger_diagnostic_logs` | 564–576 | Emits test log messages at all levels |
| `_on_tray_icon_activated` | 1075–1084 | Show/hide on tray double-click |
| `_show_tray_notification` | 1086–1090 | Show system tray balloon notification |
| `_trigger_test_notification` | 1092–1096 | Test notification |

---

## 4. Critical Signal/Slot Connection Map

⚠️ **CORRECTED**: Revision 1's checklist claimed "19 signal/slot connections." The actual count below is **38**. Every line number was re-verified.

### Internal Timer Connections (2)
```
self._icon_load_timer.timeout → self._process_icon_load_queue   (line 321)
self.clock_timer.timeout      → self._tick_clock                (line 368)
```

### TrackerSignals Bridge (2)
```
self.signals.update_signal  → self._schedule_refresh             (line 324)
self.tracker.on_update      → lambda: self.signals.update_signal.emit()  (line 371)
```

### Tray Icon (4)
```
show_action.triggered            → self.showNormal               (line 345)
self.tray_pause_action.triggered → self._on_pause                (line 348)
quit_action.triggered            → self.close                    (line 353)
self.tray_icon.activated         → self._on_tray_icon_activated  (line 356)
```

### Keyboard Shortcut (1)
```
QShortcut("Ctrl+`").activated → self._toggle_debug_console       (lines 364–365)
```

### Web Server Manager (5) — inside the `_deferred_start_web_server` closure
```
web_server_mgr.signals.goals_updated               → self._on_web_goals_updated      (405–406)
web_server_mgr.signals.alerts_toggled              → self._on_web_alerts_toggled     (408–409)
web_server_mgr.signals.theme_toggled               → self._on_web_theme_toggled      (411–412)
web_server_mgr.signals.test_notification_requested → self._trigger_test_notification (414–415)
web_server_mgr.signals.reset_requested             → self._on_web_goals_reset        (417–418)
```

### Update Checker (1)
```
self._update_signals.update_found → self._on_update_found        (line 449)
```

### Header Bar Callbacks — passed to constructor (4)
```
cmd_report       → self._show_dashboard        (line 595)
cmd_sessions     → self._show_session_manager  (line 596)
cmd_settings     → self._show_settings         (line 597)
cmd_toggle_theme → self._toggle_theme          (line 598)
```

### Control Buttons (6)
```
self.start_btn.clicked → self._on_start                 (line 643)
self.pause_btn.clicked → self._on_pause                 (line 649)
self.stop_btn.clicked  → self._on_stop                  (line 655)
self.debug_btn.clicked → self._toggle_debug_console     (line 742)
self.test_btn.clicked  → self._trigger_diagnostic_logs  (line 763)
self.bug_btn.clicked   → self._show_bug_report_menu     (line 784)
```

### Session Manager Dialog (2) — inside `_show_session_manager`
```
dialog.resume_requested      → self._resume_session            (line 1638)
dialog.view_report_requested → _on_view_report_sm (local)      (line 1644)
```

### Settings Dialog (11) — inside `_show_settings`
```
dialog.manage_categories_requested → self._show_categories_dialog    (line 2255)
dialog.about_requested             → self._show_about_dialog         (line 2256)
dialog.theme_toggled               → self.apply_theme                (line 2257)
dialog.profile_changed             → self._handle_profile_switched   (line 2258)
dialog.profile_renamed             → self._handle_profile_renamed    (line 2259)
dialog.profile_deleted             → self._handle_profile_deleted    (line 2260)
dialog.settings_imported           → self._handle_settings_imported  (line 2261)
dialog.test_notification_requested → self._trigger_test_notification (line 2262)
dialog.reload_exclusions_requested → handle_reload (local closure)   (line 2270)
dialog.rejected                    → handle_rejected (local closure) (line 2361)
dialog.settings_saved              → handle_settings_saved (local)   (line 2362)
```

**Total: 38 connections.** All must survive refactoring.

---

## 5. Instance State (Attributes Set on `self`)

All of these are read/written across multiple methods. Any extraction that splits methods across modules must share access to these:

### Tracker & Session State
- `self.tracker` — `AppTracker` instance
- `self.signals` — `TrackerSignals` instance
- `self.clock_timer` — `QTimer` (250ms tick)
- `self._last_app_state_hash` — hash for diffing app list
- `self._icon_cache` — `dict[str, QPixmap]`
- `self._icons_to_load` — `list[str]` (exe paths pending icon load)
- `self._icon_load_timer` — `QTimer` (30ms tick for icon queue)
- `self._check_vars`, `self._photo_refs`, `self._row_widgets` — UI state dicts
- `self._showing_placeholder` — bool
- `self._load_dlg` — `LoadingDialog` (set by `_on_stop` and `_show_live_report`)
- `self._app_drive_worker` — `DriveSyncWorker` (set by `_trigger_deferred_drive_sync`; guarded with `hasattr`)
- `self.web_server_mgr` — `WebServerManager` (set at 4000ms; guarded with `hasattr` in `closeEvent`)
- `self._update_signals` — `UpdateCheckSignals`
- `self.shortcut_debug` — `QShortcut`
- `self.active_profile` — str

### UI Widgets (created in `_build_ui`)
- `self.header` — `HeaderBar`
- `self.clock_label`, `self.earnings_label`, `self.active_label` — `QLabel`
- `self.start_btn`, `self.pause_btn`, `self.stop_btn` — `QPushButton`
- `self.scroll_area`, `self.scroll_widget`, `self.scroll_layout` — scroll infrastructure
- `self.list_card`, `self.footer_card` — `QFrame`
- `self.total_label` — `QLabel`
- `self.debug_btn`, `self.test_btn` — `QPushButton` (developer mode)
- `self.ver_lbl` — `FadingVersionLabel`
- `self.bug_btn` — `QPushButton`
- `self.placeholder_lbl` — `QLabel`

### Tray
- `self.tray_icon` — `QSystemTrayIcon`
- `self.tray_menu` — `QMenu`
- `self.tray_pause_action` — `QAction`

### Settings (45+ fields, loaded in `_load_app_settings`)
- `self.confirm_on_close`, `self.min_track_seconds`, `self.auto_save_seconds`
- `self.currency_symbol`, `self.hourly_rate`
- `self.idle_threshold_seconds_total`
- `self.business_name`, `self.business_emails`, `self.business_phone`, `self.business_address`, `self.business_payment`
- `self.bank_holder/account/routing/swift/name/address`
- `self.enable_bank_details`
- `self.client_name`, `self.client_emails`, `self.client_address`
- `self.business_logo_path`, `self.enable_business_logo`
- `self.qr_code_paths`, `self.qr_code_links`
- `self.mask_business_emails/phone`, `self.mask_client_emails`, `self.mask_sensitive_data`
- `self.developer_mode`, `self.dark_mode`, `self.theme_style`
- `self.weekly_goals`, `self.weekly_earnings_goal`, `self.earnings_goal_period`
- `self.enable_goal_tray_alerts`, `self.earnings_goal_reset_timestamp`
- `self.enable_distraction_auto_pause`, `self.distraction_apps`
- `self.anonymous_user_id`
- `self.posthog_client`, `self.posthog_enabled`

### Goals Runtime State
- `self.notified_goals` — `dict[str, set]` or `None`
- `self.notified_earnings_goal` — `set` or `None`
- `self.weekly_base_focus_seconds` — `dict[str, float]`
- `self.last_week_start_date` — `datetime`
- `self._goals_initialized` — `bool`
- `self._last_goal_check` — `float` (timestamp)

---

## 6. Identified Bugs & Code Smells

### 🔴 Bug: Duplicate `closeEvent` (Dead Code) — CONFIRMED BY AST

- **Lines 457–461**: First `closeEvent` waits up to 3s for `_app_drive_worker`
- **Lines 795–835**: Second `closeEvent` handles full shutdown
- AST census: 60 defs, 59 unique names, sole duplicate is `closeEvent`. The first is **unreachable**.
- **Consequence**: on exit during a background Drive sync, the worker thread is not joined. Qt may destroy the parent `QThread` mid-flight.
- **Fix**: delete lines 457–461 and insert into the second `closeEvent`, immediately before `event.accept()` at line 835:
  ```python
  if getattr(self, "_app_drive_worker", None) and self._app_drive_worker.isRunning():
      logger.info("[DriveSync] Waiting for background cloud sync thread to finish...")
      self._app_drive_worker.wait(3000)
  ```
  Place it **after** `self.web_server_mgr.stop()` (line 833) so the web server is already down. Note the second `closeEvent` calls `event.accept()`, not `super().closeEvent(event)` — keep that.

### Code Smell: Inline Dialogs (~1,028 extractable lines)
- `_show_report` (473), `_show_compact_save_dialog` (247), `_show_about_dialog` (171), `_show_categories_dialog` (137)
- These should be extracted to `dialogs/` following the existing pattern

### Code Smell: Repeated Theme Color Blocks — all four line refs verified
- `_show_about_dialog` — line 2393 (`if self.theme_style == "classic-dark":`)
- `_show_categories_dialog` — line 2565 (ternary form, `modern-dark` check)
- `_show_report` — line 2710 (`if self.theme_style == "classic-dark":`)
- `_show_compact_save_dialog` — line 3174 (`if self.theme_style == "classic-dark":`)
- **Fix**: Extract a `get_theme_colors(theme_style)` helper to `theme.py`. Note the four blocks bind **different variable sets** (`text_primary`/`text_secondary`/`border_color` vs `bg_widget`/`border_f3`), so the helper should return a dict/dataclass covering the union, not a fixed tuple.

### Code Smell: Repeated QSS Application Boilerplate — all four verified
- Lines 2382–2390, 2552–2560, 2695–2703, 3163–3171 all repeat verbatim:
  ```python
  qss = get_qss_style(self.theme_style).replace(
      "CHECKMARK_PATH", ensure_checkmark_icon(self.theme_style)
  )
  dialog.setStyleSheet(qss)
  dialog.setPalette(get_dark_palette(self.theme_style) if self.dark_mode else get_light_palette())
  ```
- **Fix**: Extract `apply_dialog_theme(dialog, theme_style, is_dark)` into `theme.py`. This is the **lowest-risk change in the whole plan** and should be done first — it is a pure 4-site substitution with no behavioural change.

### Code Smell: `_center_window` is a hidden cross-dialog dependency ⚠️ **NEW**
- Defined at line 578 on `TrueHourApp`; called from **line 327** (`__init__`, self-centering) and from three of the four extraction-target dialogs:
  - `_show_about_dialog` → line 2371 (`360, 310`)
  - `_show_categories_dialog` → line 2542 (`360, 440`)
  - `_show_report` → line 2684 (`720, 680`)
  - `_show_compact_save_dialog` → **does not use it**
- **Fix**: move `_center_window` to a shared module (`theme.py` or a new `widgets/ui_utils.py`) as a free function **before** any dialog extraction. Otherwise three extractions each need it injected.

### Code Smell: Icon Loading on Main Thread
- `_process_icon_load_queue` (line 1503) calls `get_native_icon_pixmap` synchronously on the GUI thread via a 30ms timer
- Low-risk since it processes one icon per tick, but could still cause micro-stutters with many new apps
- **Note**: `QFileIconProvider` is not documented as thread-safe. A QThread migration is **not** a drop-in change. Leave as-is; document as accepted.

### Performance: `_tick_clock` Calls Goal Check Every Tick
- `_check_weekly_goal_milestones` is called every 250ms (line 1073) but internally rate-limits to 30s (line 1157)
- The call overhead is minimal but unnecessary — could be moved to a separate 30s timer

### Performance: `posthog_client.flush()` Called Synchronously
- Line 2070: `self.posthog_client.flush()` blocks the main thread on network I/O
- Should be called asynchronously or removed (PostHog SDK auto-flushes)

---

## 7. Entry Point Analysis (Lines 3709–3788)

The `if __name__ == "__main__"` block (starts line 3709):

1. Loads `.env` via `dotenv` (in `try/except`)
2. Defines a **second** `exception_hook` at line 3719 and assigns `sys.excepthook` (shadows the module-level `handle_exception` from line 164)
3. Creates `QApplication`
4. Sets Fusion style + light palette
5. Checks for `--debug-console` argument → launches standalone debug window
6. Sets global QSS stylesheet
7. Sets global font (`Segoe UI`, 10pt)
8. Single-instance lock via `QLockFile` — **imported lazily at line 3755**, constructed at 3758
9. Creates `TrueHourApp()` and calls `.run()` (which just calls `.show()`)
10. Enters event loop, `lock_file.unlock()`, `sys.exit(exit_code)`

> [!NOTE]
> The entry point uses `QLockFile` for single-instance enforcement and handles the `--debug-console` flag for a separate window mode. Both must remain functional after refactoring.

> [!WARNING]
> **Two exception hooks exist** — `handle_exception` (line 154, installed at 164, runs on any `import app`) and `exception_hook` (line 3719, installed only under `__main__`). The second overwrites the first. This is benign today but if `app.py` becomes a thin launcher, decide which one survives rather than silently keeping both.

---

## 8. Cross-Module Import Dependencies FROM `app.py`

⚠️ **CORRECTED**: Revision 1 listed `QLockFile` in the top-level `QtCore` import. It is **not** there — it is imported lazily inside `__main__` at line 3755. `crypto` is a top-level import but sits at **line 101**, mid-file, not in the main import block.

```python
# Standard library (lines 6–14)
import io, json, logging, os, shutil, sys, time, traceback
from datetime import datetime

# PyQt6 (lines 16–37) — note: NO QLockFile here
from PyQt6.QtCore import QFileInfo, QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPixmap, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QLineEdit, QDialog, QMenu,
    QMessageBox, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QSystemTrayIcon, QFileIconProvider)

# Project modules (lines 39–72)
from tracker import AppTracker
from config import get_app_data_dir, open_file, get_app_data_root, DynamicPath
from report import (format_duration, format_duration_hms, build_report_data,
    export_txt, save_to_autosave, save_to_history, generate_session_report_html)
from version import VERSION_FULL, INFO
from assets import (GITHUB_SVG, SUN_SVG, SOLID_MOON_SVG, PLAY_SVG, PAUSE_SVG,
    BUG_SVG, SHIELD_SVG)
from debug_terminal import LogBufferCollector
from widgets.custom_widgets import SegmentedAllocationBar, AppUsageRow
from widgets.loading_dialog import LoadingDialog
from widgets.update_label import FadingVersionLabel
from workers.report_worker import ReportWorker
from theme import (FONT_FAMILY, get_tag_color, get_light_palette,
    ensure_checkmark_icon, get_svg_icon, create_minimalist_icon,
    get_qss_style, get_dark_palette)
import ctypes                                                # line 73

# Mid-file top-level import
from crypto import _get_secure_key, _encrypt_string, _decrypt_string   # line 101

# Deferred/lazy imports inside methods
from database.schema import init_db                          # __init__
from database.schema import optimize_db                      # __init__ (separate stmt)
import threading                                             # __init__ (x2)
from core.reporting.aggregator import rebuild_all_summaries  # __init__
from core.reporting.web_server import WebServerManager       # _deferred_start_web_server closure
from core.update_checker import UpdateCheckSignals, check_for_updates_async  # __init__
from version import __version__                              # __init__
from tracker import ACTIVE_SESSION_FILE                      # __init__ (line 376)
import drive_sync                                            # _trigger_deferred_drive_sync
from workers.drive_sync_worker import DriveSyncWorker        # _trigger_deferred_drive_sync
import subprocess, sys                                       # _toggle_debug_console
from tracker import _is_auto_excluded, reload_auto_excluded  # various
from report import aggregate_history_data                    # _recalculate_weekly_base_focus_seconds
from theme import PROJECT_COLORS                             # _get_web_goals_state
from dialogs.session_manager import SessionManagerDialog     # _show_session_manager
from dialogs.settings_dialog import SettingsDialog           # _show_settings
from dialogs.dashboard_dialog import TrueHourDashboard       # _show_dashboard
import posthog                                               # _init_posthog
import telemetry_config                                      # _init_posthog (try/except ImportError)
from secure_time import reset_detector                       # _reload_active_profile
from appinfo import _load_name_overrides                     # _reload_active_profile
from dotenv import load_dotenv                               # __main__
from PyQt6.QtCore import QLockFile                           # __main__ (line 3755)
```

---

## 9. Revised Implementation Plan Verification

### ❌ Issues with Original Plan

| Proposed Item | Issue |
|---|---|
| `ui/dialogs/settings_dialog.py` | Already exists at `dialogs/settings_dialog.py` |
| `ui/dialogs/session_manager.py` | Already exists at `dialogs/session_manager.py` |
| `core/workers.py` | Workers already exist at `workers/report_worker.py` and `workers/drive_sync_worker.py` |
| `core/signals.py` for `TrackerSignals` | Only 3 lines. Extraction adds import overhead for negligible benefit |
| `core/telemetry.py` | PostHog init is 36 lines with embedded API key + `telemetry_config` soft-gate. Could extract but low value |
| `ui/theme.py` | Already exists at `theme.py` (29 KB) |
| `utils/icon_utils.py` | Viable — `pil_to_pixmap` + `get_native_icon_pixmap` are pure utility functions |

### ✅ Recommended Corrected Extraction Targets — ordered by execution sequence

⚠️ **CORRECTED**: Revision 1 ordered by size. This revision orders by **dependency**, because steps 1–2 are prerequisites for steps 3–6. `core/profile_manager.py` has been **dropped** — see the rationale below.

| # | What to Extract | Lines | Target Module | Risk |
|---|---|---|---|---|
| 0 | Fix duplicate `closeEvent` | 457–461 → 835 | `app.py` (in place) | 🟢 |
| 1 | `apply_dialog_theme()` + `get_theme_colors()` helpers | 4 sites | `theme.py` (add) | 🟢 |
| 2 | `_center_window` → free function | 578–583 | `widgets/ui_utils.py` [NEW] | 🟢 |
| 3 | `_show_compact_save_dialog` | 3150–3396 (247) | `dialogs/save_dialog.py` [NEW] | 🟢 |
| 4 | `_show_about_dialog` | 2366–2536 (171) | `dialogs/about_dialog.py` [NEW] | 🟢 |
| 5 | `_show_categories_dialog` | 2538–2674 (137) | `dialogs/categories_dialog.py` [NEW] | 🟡 |
| 6 | `_show_report` | 2676–3148 (473) | `dialogs/report_dialog.py` [NEW] | 🔴 |
| 7 | `HeaderBar` class | 188–280 (93) | `widgets/header_bar.py` [NEW] | 🟢 |
| 8 | `pil_to_pixmap` + `get_native_icon_pixmap` | 86–122 (37) | `utils/icon_utils.py` [NEW] | 🟢 |
| — | ~~Profile management methods~~ | ~~3453–3700~~ | ~~`core/profile_manager.py`~~ | **DROPPED** |

**Why `core/profile_manager.py` is dropped**: the four profile methods touch **16 distinct `self.*` members** — `_last_app_state_hash`, `_load_app_settings`, `_recalculate_weekly_base_focus_seconds`, `_refresh_app_list`, `_reload_active_profile`, `_update_developer_ui`, `active_profile`, `apply_theme`, `auto_save_seconds`, `currency_symbol`, `dark_mode`, `earnings_label`, `hourly_rate`, `idle_threshold_seconds_total`, `min_track_seconds`, `tracker`. That includes a **live UI widget** (`earnings_label`) and five settings scalars written back into `self.tracker`. The only workable interface is passing the `TrueHourApp` instance itself, which relocates 247 lines without reducing coupling by one edge. Revisit only after settings are consolidated into a dataclass.

### Realistic Line Impact ⚠️ **CORRECTED**

Revision 1 claimed 1,399 extracted lines / 2,390 remaining. That subtracts gross line counts without accounting for what each move leaves behind.

| | Lines |
|---|---|
| Gross moved out (steps 2–8) | 1,158 |
| Less: call-site stubs left behind (~8 lines × 5 dialogs) | +40 |
| Less: new import statements in `app.py` | +8 |
| Plus: dead `closeEvent` removed (step 0) | −5 |
| **Net reduction in `app.py`** | **≈ 1,115** |
| **Resulting `app.py`** | **≈ 2,673 lines (−29%)** |

---

## 10. Risk Assessment for Each Extraction

⚠️ **CORRECTED**: Revision 1's coupling claims were asserted, not measured. Every row below was produced by enumerating actual `self.*` references within the method's exact line range.

| Module | Risk | **Measured** `self.*` surface | Mitigation |
|---|---|---|---|
| `dialogs/save_dialog.py` | 🟢 **Low** (was 🟡) | `dark_mode`, `theme_style` — **that's all** | Pass both as ctor args. `save_to_history` is a module import, not instance state. **Best first extraction: 247 lines for a 2-attribute interface.** |
| `dialogs/about_dialog.py` | 🟢 Low | `_center_window`, `dark_mode`, `theme_style` | Needs step 2 done first; then ctor args only |
| `dialogs/categories_dialog.py` | 🟡 Medium | `_center_window`, `_last_app_state_hash`, `_refresh_app_list`, `dark_mode`, `theme_style`, `tracker` | Mutates `tracker.tag_manager` directly. Emit a `categories_changed` signal; owner resets `_last_app_state_hash = None` and calls `_refresh_app_list()` |
| `dialogs/report_dialog.py` | 🔴 **High** (was 🟡) | `_center_window`, `_export`, **`_show_live_report`**, `dark_mode`, `theme_style` | **No `hourly_rate`/`currency_symbol`** — Rev 1 was wrong; those live in `_export` (3398–3445), whose only caller is line 3108 *inside* `_show_report`. Two callbacks must be threaded out, and `_show_live_report` re-enters `_show_report` (line 2760) — a genuine cycle. See below. |
| `widgets/header_bar.py` | 🟢 Low | Self-contained `QFrame`; no `TrueHourApp` access | Move + update import. Zero reverse-import risk (§1) |
| `widgets/ui_utils.py` | 🟢 Low | `_center_window` ignores `self` entirely | Convert to `center_window(win, width, height)` |
| `utils/icon_utils.py` | 🟢 Low | Pure functions | Move + give the module its own `logger` (see §2 caution) |

### The `_show_report` re-entrancy cycle (step 6) — read before implementing

Three inbound call sites and two outbound callbacks:

```
INBOUND   app.py:1013  _show_live_report      → _show_report(rep, is_new=False, is_live=True)
INBOUND   app.py:1641  _on_view_report_sm     → _show_report(rep, is_new=False)
                       (closure inside _show_session_manager)

OUTBOUND  app.py:3108  _show_report           → self._export(report, fmt)
OUTBOUND  app.py:2760  _show_report "Refresh" → dialog.accept(); self._show_live_report()
                                                   └─ which calls _show_report again ──┐
                                                                                        │
                       ◄────────────────────────── cycle ───────────────────────────────┘
```

Recommended interface for `ReportDialog`:

```python
class ReportDialog(QDialog):
    export_requested = pyqtSignal(object, str)   # (report, fmt)
    refresh_requested = pyqtSignal()             # owner re-runs _show_live_report

    def __init__(self, report, *, is_new=True, is_live=False,
                 theme_style="light", is_dark=False, parent=None):
        ...
```

The owner connects `refresh_requested` to a slot that closes the dialog and calls `_show_live_report()`. Do **not** let the dialog hold a reference to `TrueHourApp` and call `_show_live_report` directly — that reintroduces the cycle across a module boundary, where it is far harder to reason about.

`_export` stays on `TrueHourApp` (it needs `hourly_rate` and `currency_symbol`) and is driven by the `export_requested` signal.

---

## 11. Build System Impact

⚠️ **CORRECTED**: Revision 1 speculated that build scripts "may use `--hidden-import`". Verified — **they do not**, and there is no `.spec` file in the repo.

### Actual Build Command

`build_official.bat` (and the three sibling scripts) invoke PyInstaller directly:

```
pyinstaller --onefile --windowed --name "TrueHours_%VERSION%" --icon=icon.ico
  --add-data "icon.ico;." --add-data "templates;templates"
  --exclude-module pytest --exclude-module unittest --exclude-module tkinter
  --exclude-module pydoc --exclude-module doctest --exclude-module test
  --exclude-module setuptools --exclude-module pip --exclude-module distutils
  app.py
```

Scripts present: `build_official.bat`, `build_official_onedir.bat`, `build_unofficial.bat`, `build_unofficial_onedir.bat`, `run.bat`. **No `--hidden-import` in any of them. No `.spec` file.**

### What This Means for the Refactor

PyInstaller's static analyser follows `import` statements wherever they appear, including inside function bodies. The existing lazy `from dialogs.settings_dialog import SettingsDialog` inside `_show_settings` is already resolved this way and ships correctly today.

**Therefore no build-script change is required**, provided every new module is imported with a literal `import` / `from X import Y` statement. The one thing that would break the frozen build:

- ❌ `importlib.import_module(name)` or `__import__(name)` with a computed name — invisible to static analysis
- ❌ Dynamic dialog registries keyed by string

If either becomes necessary, add `--hidden-import dialogs.report_dialog` (etc.) to all four `.bat` files, or migrate to a `.spec` file.

### Imports That Use `getattr(sys, 'frozen', False)`
- `_init_posthog` (line 2032) — enables the embedded PostHog key at line 2044
- `_toggle_debug_console` (line 493) — chooses `[sys.executable, "--debug-console"]` when frozen vs `[sys.executable, sys.argv[0], "--debug-console"]` when not

Both must keep working. If `_toggle_debug_console` ever moves, `sys.argv[0]` must still resolve to the real entry script.

---

## 12. Verification Checklist for Implementing Agent

Run §0's four baseline checks after **every** numbered step in §9, not just at the end.

**Static**
- [ ] `python -m py_compile app.py` → OK
- [ ] `python -m pytest tests/ -q` → **94 passed** (no new failures, no reduction in collected count)
- [ ] AST census of `TrueHourApp`: unique method names = 59 minus intentional removals
- [ ] `grep -rn "from app import\|^import app" --include=*.py .` still returns **0 hits**
- [ ] No proposed new file duplicates existing `dialogs/`, `widgets/`, `workers/`, or `theme.py`

**Correctness**
- [ ] Duplicate `closeEvent` merged; drive-sync `wait(3000)` now reachable, placed after `web_server_mgr.stop()`, before `event.accept()`
- [ ] All **38** signal/slot connections in §4 preserved (count them; Rev 1's "19" was wrong)
- [ ] `_deferred_start_web_server` closure and its 5 connections moved as one unit if `__init__` is touched
- [ ] `apply_theme` still accepts **both** `bool` (line 374) and `str` (line 2359)
- [ ] Module-level side effects (log redirection, logger, `sys.excepthook`, `_force_light_mode`) still run before `QApplication`
- [ ] `utils/icon_utils.py` defines its own `logger`; does not import from `app`
- [ ] `_center_window` relocated (step 2) **before** the three dialogs that call it are extracted
- [ ] `ReportDialog` uses `export_requested` / `refresh_requested` signals; does not hold a `TrueHourApp` reference
- [ ] Both `_show_report` inbound call sites updated (lines 1013 and 1641)

**Manual smoke test** (no automated GUI coverage exists — these paths are untested by the suite)
- [ ] Start → pause → resume → stop; save dialog appears and writes history
- [ ] Dashboard button, Session Manager, Settings all open and close
- [ ] Report dialog: **Refresh** button (line 2760 path) re-opens with fresh data — the cycle in §10
- [ ] Report dialog: Export → .txt and → .html both write files
- [ ] Session Manager → "View Report" opens the report dialog
- [ ] Theme cycle light → modern-dark → classic-dark applies to main window **and** every extracted dialog
- [ ] Categories dialog: add/rename a tag → app list reflects it without restart
- [ ] Tray: double-click restore, pause action, exit action
- [ ] `Ctrl+\`` opens the debug console
- [ ] Close with an active session → confirm prompt → autosave written
- [ ] `--debug-console` flag launches the standalone window
- [ ] Second instance blocked by `QLockFile`

**Build**
- [ ] `build_official.bat` produces a working binary; new modules present in the bundle
- [ ] No `importlib`/`__import__` with computed names introduced anywhere
- [ ] Frozen build: PostHog gate and debug-console subprocess launch both still work

**Accepted, not fixed**
- [ ] `_process_icon_load_queue` main-thread icon loading documented as accepted (`QFileIconProvider` thread-safety is unverified; QThread migration is not a drop-in)
- [ ] `posthog_client.flush()` (line 2070) flagged for async migration — out of scope for this refactor
- [ ] `_check_weekly_goal_milestones` called at 250ms with a 30s internal gate — flagged, not changed

---

## 13. Verification Method & Provenance

This revision was produced by checking the document against the working tree, not by re-reading the document.

| Claim class | How verified |
|---|---|
| Method boundaries | `grep -n "^(class \|def \|    def )" app.py` — all 60 defs |
| Method census / duplicate detection | `ast.parse` + `Counter` over `TrueHourApp.body` |
| Signal connections | `sed -n` on each cited line range; all 38 read directly |
| Coupling surfaces (§10) | `sed -n 'START,ENDp' app.py \| grep -o "self\.[a-zA-Z_]*" \| sort -u` per method |
| Call-site maps | `grep -n "_show_report(\|_export(\|_center_window(\|_show_compact_save_dialog("` |
| Reverse imports | `grep -rn "from app import\|^import app" --include=*.py .` |
| Build config | Read all four `build_*.bat`; `ls *.spec` → none |
| Baseline health | `py_compile`, 25-module import loop, `pytest tests/ -q` |

**Corrections applied in Revision 2**: line count 3,789 → 3,788; added `_show_settings` (2207–2364) and `_show_live_report` (994–1025) to the inventory; documented the `_show_report` ↔ `_show_live_report` re-entrancy cycle; corrected `_show_report`'s coupling surface (no `hourly_rate`/`currency_symbol`); downgraded `save_dialog` to 🟢 and promoted it to first extraction; upgraded `report_dialog` to 🔴; added `_center_window` as a prerequisite step; dropped `core/profile_manager.py`; signal count 19 → 38; removed `QLockFile` from the top-level import list; replaced the speculative build section with the actual PyInstaller command; re-sequenced §9 by dependency rather than size; recomputed line-impact math.

**Not changed** — these Revision 1 claims were checked and found correct: every top-level function and method line range; all four QSS boilerplate sites (2382/2552/2695/3163); all four theme-color-block sites (2393/2565/2710/3174); PostHog key at 2044; `flush()` at 2070; frozen checks at 2032 and 493; entry point at 3709; the duplicate-`closeEvent` diagnosis; the §1 already-extracted module tree; `utils/` not existing.
