# Changelog

All notable changes to TrueHour will be documented in this file.

## [Unreleased]

### Added
- **Session Merging**: Select multiple sessions in Session Manager, combine total tracked durations, app breakdowns, timelines, and activity logs into a single merged session JSON file with custom naming.
- **Automatic Cleanup**: Original source sessions are automatically moved to Trash upon successful merge.
- **Manual Additional Payments & Fees on Invoices**: Added manual payment input fields (Amount & Description) to invoice generation options, rendering custom line items and adjusting grand totals.
- **Expanded Selection Support**: Enabled session selection checkboxes on both Sessions and Recoveries tabs in Session Manager.

### Fixed
- **Resumed Session Overwrite Issue**: Fixed bug where saving a resumed session generated a duplicate file by preserving `resumed_filepath` on `AppTracker` and saving in-place.
- **Merge Minimum Threshold**: Enforced a minimum requirement of 2 sessions for merge operations to prevent single-session duplication.
