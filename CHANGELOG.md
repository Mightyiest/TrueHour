# Changelog

All notable changes to TrueHour will be documented in this file.

## [4.0.0-beta.4] - 2026-08-02

### Added
- **Refactoring & Architectural Audit Verification**: Complete code structure audit and verification document for modularizing `app.py` without breaking existing PyQt6 functionality or UI signals.

### Fixed
- **Drive Sync Worker Shutdown**: Resolved unjoined background cloud sync thread bug on application close.

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
