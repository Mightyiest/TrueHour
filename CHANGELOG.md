# Changelog

All notable changes to TrueHour will be documented in this file.

## [4.0.0-beta.4] - 2026-08-02

### Added
- **`app.py` Core Codebase Refactoring**: Modularized 3,788-line monolithic `app.py` down to 2,258 lines (-40% line reduction) by extracting dialogs, widgets, and utility helpers into decoupled modules (`widgets/ui_utils.py`, `utils/icon_utils.py`, `widgets/header_bar.py`, `dialogs/save_dialog.py`, `dialogs/about_dialog.py`, `dialogs/categories_dialog.py`, `dialogs/report_dialog.py`).
- **Local Web Server Token Security**: Integrated 128-bit secret token validation (`auth_token` and `X-TrueHour-Token` header) for all local web server POST endpoints to protect against unauthorized CSRF/cross-origin requests and local script manipulation.

### Fixed
- **Drive Sync Worker Shutdown**: Resolved unjoined background cloud sync thread bug on application close.
- **Web Dashboard Theme Isolation**: Decoupled Web Goals Studio theme toggle from desktop UI styles, storing dashboard preferences in local storage.
- **Web Server Token Routing & Port Fallback**: Fixed 404 handler issue when launching local web dashboard with authentication query parameters and prioritized default port 5080.

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
