---
name: release-publisher
description: Workflow for synchronizing application releases across build scripts, CHANGELOG.md, README.md, docs/index.html, and Git release branches.
---

# Release Publisher Skill

Use this skill when preparing, tagging, building, or publishing new releases for TrueHour or similar desktop applications.

## Workflow Directives

When completing a feature, bug fix, or codebase refactoring:

### 1. Build Script Synchronization
- Ensure build scripts (`build_official.bat`, `build.sh`, `build_official_onedir.bat`) accurately reflect current flags and dependencies.
- Remove obsolete build-time injections or flags that no longer apply.

### 2. CHANGELOG.md Updates
- Add explicit, structured bullet points under the target release header (`## [X.Y.Z-beta.N] - YYYY-MM-DD`).
- Group changes logically under `### Added`, `### Fixed`, `### Changed`, and `### Removed`.

### 3. README.md Updates
- Keep feature matrices, security tables, and FAQ answers in sync with current application behavior.
- Ensure privacy and offline capability claims accurately reflect the codebase.

### 4. `docs/index.html` Landing Page Synchronization
- Add the new version block at the top of the `#paneChangelog` list in `docs/index.html`.
- Match version tags (`<span class="changelog-tag beta">Beta</span>` or `stable`).
- Highlight key user-facing features, security upgrades, and performance refactoring.

### 5. Obsolete Document Cleanup
- Remove completed implementation plans (e.g. `docs/*_verification.md`) once fully executed and verified.

### 6. Git Branch & Remote Push
- Run verification tests (`python -m py_compile app.py`, `python -m pytest tests/`).
- Stage changed files, commit with conventional commit messages (`refactor:`, `feat:`, `fix:`, `docs:`), and push to the remote release branch (`origin/v4-beta.4`).
