# TrueHour v5.0.0 (Native Rust Edition)

> **A lightweight, 100% local-only desktop focus & time tracker for Windows, built natively in Rust with `egui` / `eframe` — zero WebView2, zero Chromium, zero telemetry.**

TrueHour monitors your active foreground application to track productive work time, calculate earnings from hourly rates, assign project categories, and generate verified session reports and printable HTML invoices.

![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-0078D4.svg)
![Platform](https://img.shields.io/badge/platform-Windows-0078D4?logo=windows)
![Rust](https://img.shields.io/badge/rust-eframe%200.37%20%7C%20glow-DEA584?logo=rust)
![Local Only](https://img.shields.io/badge/mode-100%25%20Local--Only-10B981)

---

## ✨ Key Features

| | Feature | Description |
|---|---|---|
| ⚡ | **Pure Native GUI** | Built with `egui 0.37` + `eframe 0.37` (`glow` OpenGL). Launches fast, uses ~85 MB RAM, and spawns **zero** WebView2 / Chromium child processes. |
| 🕒 | **Precision Time Tracking** | Polls the active Windows foreground process, tracks counted vs. total session time, and supports retroactive idle deduction. |
| 🚫 | **Distraction Auto-Pause** | Automatically pauses tracking on distracting apps (configurable checklist or right-click app row context menu) and resumes when you return to work. |
| 🏷️ | **Project Categories** | Color-coded category pills, live category reassignment, custom categories, and persistent app mappings. |
| 📊 | **Analytics Dashboard** | Built-in Trends & History insights, weekly focus goal tracking, and activity heatmap. |
| 🧾 | **Session Manager & Invoices** | Multi-tab manager (`Sessions`, `Recoveries`, `Trash`, `Invoices`), session merging, invoice status lifecycle (`DRAFT` / `UNPAID` / `PAID`), QR codes, and browser preview. |
| 📄 | **HTML Templates** | Editable A4 HTML invoice and session report templates in `templates/` with automatic runtime self-healing if missing. |
| 🔒 | **Anti-Tamper SHA-256 Ledger** | Monotonic clock checks, NTP drift verification, and SHA-256 hash-chained session ledger. |
| 🔐 | **Encrypted Local Backups** | Export/import `.truehour` workspace or single-profile archives with optional password encryption (PBKDF2-HMAC-SHA256 + Fernet). |
| 🎨 | **Three Built-In Themes** | Switch live between **Modern Dark**, **Classic Dark**, and **Light** themes with matching system tray integration. |
| 🛡️ | **Offline & Privacy-First** | Zero telemetry, zero cloud sign-in, single-instance lock, and automatic self-exclusion by PID. |

---

## 🚀 Building & Running

### Option 1: Build on GitHub Actions (Saves Local Disk Space)

You do not need to keep Rust or `target/` build caches on your PC:

1. Push changes to `v5.0-rust` (or `main`/`master`), **or** open the **Actions** tab on GitHub and run **Build TrueHour (Windows Native)** manually (`workflow_dispatch`).
2. Download the **`truehour-windows-x64`** artifact (`truehour.exe`, ~13 MB) from the completed workflow run.

Workflow definition: [`.github/workflows/build.yml`](.github/workflows/build.yml).

### Option 2: Build Locally from Source (Windows)

Prerequisites: [Rust toolchain](https://rustup.rs/) (`stable`) with MSVC build tools.

```powershell
cd truehour-rs
cargo test --no-fail-fast
cargo build --release
```

The standalone binary is produced at:
`truehour-rs/target/release/truehour.exe`

To reclaim local disk space after copying `truehour.exe` elsewhere:

```powershell
cd truehour-rs
cargo clean
```

---

## 📂 Project Structure (`v5.0-rust` Branch)

```text
TrueHour/
├── .github/workflows/
│   └── build.yml               # Windows CI build + truehour.exe artifact upload
├── truehour-rs/                # Native Rust application crate
│   ├── Cargo.toml
│   ├── build.rs                # Windows icon & version resource embedding
│   ├── icons/                  # App icon assets
│   ├── src/
│   │   ├── main.rs             # Windows GUI entry point
│   │   ├── lib.rs              # AppCore orchestration, settings, lifecycle
│   │   ├── tracker.rs          # Foreground polling, idle & distraction auto-pause
│   │   ├── appinfo.rs          # Win32 process/title/icon resolution
│   │   ├── report.rs           # Session JSON persistence, merging, TXT/HTML export
│   │   ├── invoice.rs          # HTML invoice generation & formatting
│   │   ├── db.rs               # SQLite summaries & invoice records
│   │   ├── backup.rs           # .truehour ZIP workspace/profile backup & restore
│   │   ├── crypto.rs           # PBKDF2 + Fernet encryption parity
│   │   ├── secure_time.rs      # SHA-256 hash chain & NTP drift validation
│   │   ├── http_preview.rs     # Localhost-only invoice preview server
│   │   ├── tray.rs             # Native Windows system tray menu
│   │   └── gui/                # Pure egui/eframe native windows, modals & widgets
│   └── tests/
│       └── integration_parity.rs
├── templates/                  # Editable A4 HTML invoice & report templates
├── README.md
└── LICENSE.md
```

*(Legacy Python v4.2 source files remain in the repository root for reference and migration parity; `truehour-rs` does not require Python at runtime.)*

---

## ⚙️ Data & Configuration

TrueHour stores profiles, settings, SQLite summaries, sessions, invoices, QR codes, and templates locally under:

`%LOCALAPPDATA%\TrueHour`

- **Profiles:** Switch, create, rename, or delete isolated workspaces in **Settings → General & Controls**.
- **Auto-Exclusions & Name Overrides:** Edit `auto_excluded_apps.txt` or `name_overrides.txt` directly from Settings and click **Reload**.
- **Templates:** Customize `templates/invoice.html` or `templates/report_template.html` — missing files are regenerated automatically at runtime.

---

## ❓ FAQ

**Q: Does TrueHour v5.0 use WebView2 or Chromium?**  
A: **No.** It is a pure native Rust binary rendered with `egui`/`eframe` (`glow`). No WebView2 or browser processes are spawned.

**Q: Does it send any data online?**  
A: **No.** TrueHour v5.0 runs in 100% Local-Only Mode with zero telemetry, zero analytics, and no cloud account sync.

**Q: Why is `target/` so large after building locally?**  
A: Rust/Cargo stores intermediate compiler artifacts in `truehour-rs/target/`. Copy `truehour-rs/target/release/truehour.exe` to a safe folder and run `cargo clean` (or build on GitHub Actions instead).

---

## 📄 License

This project is licensed under the **PolyForm Noncommercial License 1.0.0**.

See [LICENSE.md](LICENSE.md) for the full legal text.

---

## 🙏 Acknowledgments

- Built in **Rust** with **egui / eframe**, **rusqlite**, and **windows-rs**.
- Vectors and icons by <a href="https://dribbble.com/saeedworks?ref=svgrepo.com" target="_blank">Saeedworks</a> (CC Attribution License via <a href="https://www.svgrepo.com/" target="_blank">SVG Repo</a>).
- AI coding assistance from Claude, Gemini, Qwen, and DeepSeek.
