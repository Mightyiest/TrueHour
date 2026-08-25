# Implementation Plan — TrueHour Free Edition (`v4-beta.4-free`)

This plan outlines the technical changes required to create the **TrueHour Free Edition** on branch `v4-beta.4-free` by **completely stripping (deleting) Pro/Cloud code modules** and adding fancy "Upgrade to Pro" callout buttons linking to `https://mightyiest.github.io/TrueHour/`, while retaining core anti-tamper tracking, invoicing, bank details, QR codes, and Classic Dark theme.

---

## Feature Comparison Table

| Feature / Capability | Free Edition (`v4-beta.4-free`) | Pro Edition (`v4-beta.4`) |
|---|:---:|:---:|
| **Automatic App Switch Tracking** | ✅ Included | ✅ Included |
| **Monotonic Anti-Tamper Clock** | ✅ Included | ✅ Included |
| **Unlimited Local Session History** | ✅ Included | ✅ Included |
| **Plain Text Report Export (`.txt`)** | ✅ Included | ✅ Included |
| **Verified SHA-256 Audit Ledger** | ✅ Included | 🛡️ **Cryptographic Proof of Work** |
| **Professional HTML/PDF Invoice Builder** | ✅ Included | 🧾 **Custom Logos, Headers & Terms** |
| **Bank Details & Payment QR Codes** | ✅ Included | 💳 **Embedded SWIFT/IBAN & QR Codes** |
| **Clean Light & Classic Dark Themes** | ✅ Included | 🎨 **Clean Light & Classic Dark** |
| **Single Client Billing Profile** | ✅ Included | ✅ Included |
| **Google Drive Cloud Sync & Restore** | 🔒 Fancy Upgrade Button | ☁️ **OAuth 2.0 PKCE 1-Click Sync** |
| **Invoice Additional Fees & Expenses** | 🔒 Fancy Upgrade Button | ➕ **Custom Expense Line Items** |
| **Multi-Session Merging** | 🔒 Fancy Upgrade Button | 📁 **Combine Sessions into 1 File** |
| **App Distraction Auto-Pause** | 🔒 Fancy Upgrade Button | 🛑 **App Blacklisting & Auto-Resume** |
| **Multi-Profile Management** | 🔒 Fancy Upgrade Button | 👥 **Unlimited Business Profiles** |
| **Modern Dark Theme (Vibrant)** | 🔒 Fancy Upgrade Button | 🎨 **Modern Dark Theme** |
| **Goals Studio Pro Analytics** | Basic Hours Only | 📊 **Full Revenue Targets & Heatmaps** |

---

## Code Stripping Directives

> [!IMPORTANT]
> **Complete Code Removal Strategy**:
> - All Pro code, dialog classes, and helper functions will be **completely removed** (not merely commented out).
> - Dedicated Pro modules (`drive_sync.py`, `dialogs/drive_sync_dialog.py`, `dialogs/distraction_dialog.py`, `dialogs/merge_dialog.py`) will be **deleted (`git rm`)**.
> - UI slots will display a styled **"✨ Upgrade to Pro"** button that opens `https://mightyiest.github.io/TrueHour/`.

---

## Proposed Changes

### Core Logic & Versioning

#### [MODIFY] [version.py](file:///c:/Users/ownin/Documents/Antigravity%20Projects/TrueHour/version.py)
- Set version string to `4.0.0-beta.4-free`.
- Add `IS_PRO_EDITION = False` constant.

---

### Pro Module Deletions (`git rm`)

#### [DELETE] `drive_sync.py`
- Completely remove Google Drive OAuth 2.0 PKCE authentication and sync worker engine.

#### [DELETE] `dialogs/drive_sync_dialog.py`
- Completely remove Google Drive cloud sync modal dialog.

#### [DELETE] `dialogs/distraction_dialog.py`
- Completely remove Distraction Apps checklist dialog.

#### [DELETE] `dialogs/merge_dialog.py`
- Completely remove multi-session merge dialog.

---

### Core UI & App Stripping

#### [MODIFY] [app.py](file:///c:/Users/ownin/Documents/Antigravity%20Projects/TrueHour/app.py)
- Remove Google Drive sync initialization, background sync threads, and menu items.
- Place a styled **"✨ Pro Cloud Sync"** button in header bar linking to `https://mightyiest.github.io/TrueHour/`.

#### [MODIFY] [dialogs/export_dialog.py](file:///c:/Users/ownin/Documents/Antigravity%20Projects/TrueHour/dialogs/export_dialog.py)
- Strip manual fee/expense input fields and replace with an **"✨ Unlock Expense Line Items (Pro)"** button.
- Retain full HTML/PDF Invoice, Receipt, Bank details, and QR code generation options.

#### [MODIFY] [dialogs/save_dialog.py](file:///c:/Users/ownin/Documents/Antigravity%20Projects/TrueHour/dialogs/save_dialog.py)
- Replace "Merge Selected Sessions" button with a **"✨ Multi-Session Merging (Pro)"** button linking to `https://mightyiest.github.io/TrueHour/`.

#### [MODIFY] [dialogs/settings_dialog.py](file:///c:/Users/ownin/Documents/Antigravity%20Projects/TrueHour/dialogs/settings_dialog.py)
- Replace Distraction Apps button with a **"✨ Distraction Auto-Pause (Pro)"** button.
- Restrict Theme options to "Clean Light" and "Classic Dark", displaying a **"✨ Modern Dark (Pro)"** callout for the vibrant dark theme.
- Replace Multi-Profile selector with a **"✨ Multi-Profile Billing (Pro)"** button.

---

## Verification Plan

### Automated Tests
- `python -m py_compile app.py`
- `python -m pytest tests/ -v`

### Manual Verification
1. Launch `python app.py` on `v4-beta.4-free` branch.
2. Confirm deleted Pro modules (`drive_sync.py`, `dialogs/drive_sync_dialog.py`, etc.) are absent.
3. Verify fancy upgrade buttons open `https://mightyiest.github.io/TrueHour/` in browser.
4. Verify core time tracking, SHA-256 ledger, HTML invoicing, bank details, QR codes, and Classic Dark theme work cleanly.
