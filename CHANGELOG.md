# Changelog

All notable changes to TrueHour will be documented in this file.

## [4.2.0-beta.1] - 2026-10-10

### Added
- **Google Drive 200-Revision Auto-Rotation & Pruning**: Automated revision unpinning and fallback recovery for Google Drive `keptRevisionsLimitExceeded` (HttpError 403) errors, keeping pinned revisions below quota without dropping cloud backups.
- **SQLite WAL Online Backup Architecture**: Migrated database backup creation to `sqlite3.Connection.backup()` ensuring committed WAL frames are flushed into clean, standalone database files, and automated cleanup of stale `-wal` and `-shm` files during profile restorations.
- **Zero-Leak Portable Cloud Encryption**: Re-keyed cloud backup banking data with portable PBKDF2 derivation based on account ID, preventing hardware SID locking across PCs while keeping plaintext off disk.
- **Multi-Profile Unified Cloud Backup Architecture**: Consolidated multi-profile `.truehour` archive sync to Google Drive, ensuring all profiles and tracking histories are backed up together atomically.
- **Drive Anti-Overwrite Safety Gate**: Implemented cloud timestamp and integrity verification gates to safeguard existing cloud backups from being prematurely overwritten.
- **Automated Audit & UI Dialog Stability Test Suites**: Added 30 dedicated regression tests in `tests/test_audit_fixes.py` and `tests/test_ui_dialog_stability.py` validating 40 codebase audit findings (142 tests total, 100% green).

### Fixed
- **PyQt6 Background Worker Thread Lifecycle**: Protected `SettingsDialog`, `CloudRevisionsDialog`, and `LoadingDialog` against destroyed `QThread` segmentation faults by disconnecting and stopping workers on dialog close, accept, and reject.
- **Forward Clock Jump Bypass in Tamper Detection**: Verified forward system clock jumps (>5s) against network NTP time before adjusting sleep durations and wrapped cryptographic chain validation in re-entrant thread locks.
- **Settings Load Encoding & Destructive Reset Prevention**: Added explicit UTF-8 encoding in `_load_app_settings()`, preserved corrupt files to `.corrupt.bak`, and performed atomic writes via `.tmp` and `os.replace()`.
- **UI Category Reassignment on Scroll**: Implemented `NoWheelComboBox` in categories dialog to block accidental category mutation during mouse-wheel scrolling.
- **Manual Line Items on Paid Receipts**: Included `additional_items` in invoice database amounts and rendered itemized fees in paid HTML receipts.
- **UI Crash & Memory Access Violation (0xC0000005)**: Resolved Windows `STATUS_ACCESS_VIOLATION` in `Qt6Core.dll` (`QObject::isWidgetType()`) caused by unsafe `setParent(None)` calls on widgets while active mouse release signals were still dispatching.
- **Nested Modal Hierarchy & Window Modality**: Correctly parented `CategoriesDialog` and `AboutDialog` to `SettingsDialog` when launched from settings, eliminating competing modal event loops under the main window root.
- **Deferred Layout Rebuilding**: Deferred category, app list, and QR thumbnail rebuilds using `QTimer.singleShot(0, ...)` so Qt event loops unwind cleanly before widgets are destroyed and recreated.
- **Layout Item & Spacer Memory Leaks**: Cleanly deleted `QLayoutItem` and `QSpacerItem` instances when taking items from layouts during refreshes.
- **Version Label Animation State Machine**: Streamlined `FadingVersionLabel` crossfade transitions to a unified state-driven model, removing nested dynamic lambda connections on `finished` signals.
- **Early QObject Lifecycle Compliance**: Lazily initialized `LogSignalEmitter` in `LogBufferCollector` so `QObject` instances are never created before `QApplication` initialization.

## [4.1.0-beta.1] - 2026-08-25

### Added
- **Multi-Trigger Automatic Google Drive Cloud Sync**: Continuous background cloud backup engine that automatically pushes single-archive `.truehour` backups to Google Drive on session completion/save, every 30 minutes in the background, 6 seconds post-startup, and immediately prior to application exit.
- **Cross-Profile Authentication Portability**: Upgraded token management in `drive_sync.py` to discover and synchronize OAuth 2.0 credentials across active profile directories and root app data, preventing accidental sign-outs when switching profiles.

### Fixed
- **Cloud Auto-Sync Default State**: Resolved configuration default mismatch where Google Drive auto-sync showed as enabled in UI but evaluated to `False` in backend settings loaders.
- **PyQt6 Framework Consistency in Tests**: Fixed stray PySide6 imports in `test_drive_sync.py` to maintain full test suite compatibility on PyQt6.

## [4.0.0-beta.4] - 2026-08-02

### Added
- **`app.py` Core Codebase Refactoring**: Modularized 3,788-line monolithic `app.py` down to 2,258 lines (-40% line reduction) by extracting dialogs, widgets, and utility helpers into decoupled modules (`widgets/ui_utils.py`, `utils/icon_utils.py`, `widgets/header_bar.py`, `dialogs/save_dialog.py`, `dialogs/about_dialog.py`, `dialogs/categories_dialog.py`, `dialogs/report_dialog.py`).
- **Local Web Server Token Security**: Integrated 128-bit secret token validation (`auth_token` and `X-TrueHour-Token` header) for all local web server POST endpoints to protect against unauthorized CSRF/cross-origin requests and local script manipulation.

### Fixed
- **Drive Sync Worker Shutdown**: Resolved unjoined background cloud sync thread bug on application close.
- **Web Dashboard Theme Isolation**: Decoupled Web Goals Studio theme toggle from desktop UI styles, storing dashboard preferences in local storage.
- **Web Server Token Routing & Port Fallback**: Fixed 404 handler issue when launching local web dashboard with authentication query parameters and prioritized default port 5080.

### Removed
- **PostHog Telemetry & Dependencies**: Completely purged PostHog analytics tracking, telemetry configuration files, and `posthog` package dependencies, converting TrueHour to a 100% telemetry-free, offline-first application.

## [4.0.0-beta.1] - 2026-07-30

### Added
- **Google Drive Cloud Sync & Login**: Integrated OAuth 2.0 PKCE desktop authentication with single-archive `.truehour` ZIP package uploading & 1-click cloud restoration directly to/from user's Google Drive.
- **Bank Transfer Details Integration**: Preserved bank account holder, routing, SWIFT, and bank address details in backups and Google Drive cloud sync packages.
- **Session Merging**: Select multiple sessions in Session Manager, combine total tracked durations, app breakdowns, timelines, and activity logs into a single merged session JSON file with custom naming.
- **Manual Additional Payments & Fees on Invoices**: Added manual payment input fields (Amount & Description) to invoice generation options, rendering custom line items and adjusting grand totals.

### Fixed
- **Billing & Invoice Restore Reload**: Implemented signal handlers in main application to immediately reload restored billing profiles, headers, logos, and QR codes into active memory after cloud restore.
- **Chronological Session Sorting**: Implemented internal session date/time parsing (`_get_session_timestamp`) so restored backup sessions sort strictly chronologically (latest sessions on top, oldest on bottom).
- **Windows File Locking Crash Fix**: Replaced destructive `shutil.rmtree()` in backup manager with safe file copying exception guards to prevent `0xC0000409` crashes on active SQLite WAL files.
- **Resumed Session Overwrite Issue**: Fixed bug where saving a resumed session generated a duplicate file by preserving `resumed_filepath` on `AppTracker` and saving in-place.
