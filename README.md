# True Hours v3.0.0

> **A lightweight, privacy-first desktop time tracker with a modern Fluent Design UI, supporting Windows & macOS.**

True Hours automatically monitors your active window to track productivity, calculate earnings based on hourly rates, and generate detailed session reports. It features crash recovery, auto-exclusion of system apps, customizable external HTML templates, offline app icon extraction, and flexible export options (TXT, HTML).

![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-0078D4.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-0078D4?logo=windows)
![Python](https://img.shields.io/badge/python-3.8+-3776AB?logo=python)

---

## ✨ Features

| | Feature | Description |
|---|---|---|
| 🕒 | **Time Tracking** | Detects the foreground app and logs usage with second-level precision. |
| 📊 | **Analytics Dashboard** | Interactive PyQt6 donut & bar charts with live and historical category breakdowns. |
| 📄 | **HTML Templates** | Editable invoice and session report templates in `templates/` — easy to customize externally. |
| 🩺 | **Self-Healing Templates** | Missing template files are auto-regenerated at runtime, preventing crashes. |
| 🧾 | **Invoice Builder** | Dynamic invoicing with multi-email chip inputs, masked addresses, QR code graphics, and A4 PDF printing. |
| 💰 | **Earnings Calculator** | Set an hourly rate and watch earnings accumulate live during active sessions. |
| 🛡️ | **Smart Exclusions** | Auto-ignores system processes; manually exclude apps (e.g. Spotify) from work time. |
| 🔒 | **Anti-Tamper Security** | Monotonic clock protection, NTP validation, and SHA-256 hash chaining with real-time integrity scoring. |
| 💾 | **Crash Recovery** | Unexpected closures are auto-saved to an `autosave` folder for later recovery. |
| 📤 | **Export Options** | Export to TXT, HTML Invoice, or HTML Session Report. |
| 🎨 | **Modern UI** | Clean, light-themed interface inspired by Windows 11 Fluent Design, built with PyQt6. |
---

## 📸 Screenshots
<div align="center">
  <strong>True Hours Interface</strong><br>
  <em>Main Tracker, Session Report, and Dashboard</em><br><br>
<img width="2559" height="1397" alt="True Hours Full Window Interface" src="https://github.com/user-attachments/assets/dd4390b7-031a-46a8-84fa-39dd6ea11053"/>
  
  <br><br><br>

  <strong>Generated Invoice</strong><br>
  <em>Professional HTML invoice output</em><br><br>
<img width="2559" height="1347" alt="True Hours HTML Invoice" src="https://github.com/user-attachments/assets/48288caf-6ab9-43eb-bd36-e303ab229450" />
</div>

---

## 🚀 Installation & Usage

### Option 1: Run from Source (Recommended for Developers)

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/yourusername/TrueHours.git
    cd TrueHours
    ```

2.  **Install Dependencies:**
    *   **Windows:**
        ```bash
        pip install PyQt6 pywin32 psutil Pillow
        ```
    *   **macOS:**
        ```bash
        pip install PyQt6 pyobjc-framework-AppKit psutil Pillow
        ```

3.  **Run the Application:**
    *   **Windows:** Use the batch file `run.bat` or run:
        ```bash
        python app.py
        ```
    *   **macOS:** Run the shell launcher script `./run.sh` (or manually run `python3 app.py`):
        ```bash
        chmod +x run.sh
        ./run.sh
        ```

### Option 2: Build Standalone Executable (.exe or .app)

If you want to package a standalone binary that runs without requiring Python to be installed:

1.  **Install PyInstaller:**
    ```bash
    pip install pyinstaller
    ```

2.  **Build Binary:**
    *   **Windows:**
        Double-click `build.bat` or run:
        ```bash
        pyinstaller --noconsole --onefile --windowed --name="TrueHours" --icon="icon.ico" app.py
        ```
    *   **macOS:**
        Run the build script `./build.sh` (or manually run `pyinstaller`):
        ```bash
        chmod +x build.sh
        ./build.sh
        ```
        *(This automatically installs dependencies, runs PyInstaller, cleans up temp files, and places a standard double-clickable `TrueHours.app` bundle in your root directory!)*

---

## 📂 Project Structure

```text
TrueHours/
├── icon.ico            # Application Icon
├── app.py              # Main UI Entry Point (PyQt6)
├── tracker.py          # Core Logic: Polling loop, state management, crash recovery
├── report.py           # Data formatting, export utilities (TXT/HTML)
├── appinfo.py          # Windows API wrappers: Get foreground window, extract icons/names
├── config.py           # Configuration helpers: Data directory management
├── secure_time.py      # Anti-tamper security: Monotonic clocks, hash chaining, NTP sync
├── run.bat             # Windows launcher script
├── run.sh              # macOS/Linux launcher script
├── build.bat           # Automated Windows PyInstaller build script
├── build.sh            # Automated macOS PyInstaller build script
├── requirements.txt    # Python dependencies
├── README.md           # This file
├── SECURITY_FEATURES.md # Detailed documentation of anti-tamper protections
├── templates/          # A4 HTML templates (invoices, session reports)
...
```

---

## ⚙️ Configuration & Customization

True Hours stores user data in the local app data directory:
`%LOCALAPPDATA%\TrueHour` (or `~\TrueHour` if env var is missing).

### 1. Auto-Excluded Apps
True Hours comes with a default list of system apps to ignore (e.g., `explorer.exe`, `svchost.exe`). You can customize this list.

1.  Open **Settings** in the app.
2.  Click **"Edit Auto-Exclusions"**.
3.  This opens `auto_excluded_apps.txt`.
4.  Add or remove `.exe` names (one per line). Lines starting with `#` are comments.
5.  Click **"Reload"** in Settings to apply changes immediately without restarting.

### 2. Name Overrides
If an app displays a confusing technical name (e.g., `chrome.exe` instead of `Google Chrome`), you can force a friendly name.

1.  Open **Settings**.
2.  Click **"Edit Name Overrides"**.
3.  Format: `exename=Friendly Name`
    ```text
    chrome=Google Chrome
    code=VS Code
    ```

### 3. Billing Settings
Set your currency and hourly rate in the **Settings** menu.
*   **Currency Symbol:** Choose from USD, EUR, GBP, JPY, etc.
*   **Hourly Rate:** Enter your rate (e.g., `50.00`).
*   *Note:* Earnings are calculated based on **Counted Work Time** only (excluded apps do not earn money).

### 4. Custom HTML Templates (A4 Layouts)
True Hours allows you to fully customize how client invoices and session reports look when printed to PDF or exported.
1.  Open the `templates/` folder in the True Hours root directory.
2.  Open **`invoice.html`** or **`report_template.html`** in a code/text editor (e.g., VS Code).
3.  Modify the styling (CSS), fonts, layout structures, and text as you like.
4.  Keep placeholders in place (e.g., `{{BUSINESS_NAME}}`, `{{ITEMS}}`, `{{TIMELINE_ITEMS}}`) so the application can dynamically populate your tracking details.
5.  *Self-Healing:* If you ever make a mistake or break a file, simply delete the file or the `templates/` directory, and True Hours will instantly recreate a fresh default copy at runtime.

---

## 📊 Understanding the Data

### Session States
*   **Total Session Time:** The entire duration from Start to Stop/Pause.
*   **Counted Work Time:** Time spent in apps that are **not** excluded. This is the basis for earnings calculations.
*   **Excluded Apps:** Apps you have manually or automatically marked as "non-work." They appear in the report but are marked `[EXCLUDED]` and do not contribute to earnings.

### File Storage
*   **`sessions/`**: Contains manually saved session reports (`.json`).
*   **`autosave/`**: Contains automatic backups every 10 seconds (configurable) and crash recoveries.
*   *Files prefixed with `auto_`: Regular backups.
*   *Files prefixed with `recovery_`: Sessions recovered after a crash.

---

## 🛠️ Developer Guide

### Key Modules

#### `tracker.py`
The heart of the application.
*   **`AppTracker` Class:** Manages the polling thread.
*   **`_poll_loop()`:** Runs every 1 second (default). Checks `get_foreground_app_info()`.
*   **Crash Recovery:** Uses `active_session.json` to store state. If the app restarts and finds this file, it offers to recover the session.

#### `appinfo.py`
Handles Windows-specific interactions.
*   **`get_foreground_app_info()`:** Uses `win32gui` and `psutil` to find the active window's PID and executable path.
*   **`resolve_name()`:** Tries to get the "File Description" from the EXE version info for a friendly name. Falls back to overrides or filename.
*   **`get_icon_image()`:** Extracts the small icon from the EXE using `win32gui.ExtractIconEx` and converts it to a PIL Image for PyQt6.

#### `report.py`
Handles data serialization.
*   **`build_report_data()`:** Aggregates raw tracker data into a structured dictionary.
*   **`export_txt()`:** Generates a clean text file summary of the session.
*   **`save_to_autosave()`:** Atomic write to prevent corruption during crashes.

### Adding New Features

1.  **New Export Format:** Add a function in `report.py` (e.g., `export_pdf`) and call it from `app.py`'s `_export` method.
2.  **Dark Mode:** Currently, the app forces Light Mode via `ctypes` in `app.py`. To support Dark Mode, you would need to dynamically switch the `BG_*` color constants and remove the `SetPreferredAppMode(3)` call.

---

## ❓ FAQ

**Q: Why is my timer not updating?**

A: Ensure the app has permission to run in the background. Some "Game Modes" or aggressive power savers may pause Python scripts.

**Q: How do I stop tracking specific games or social media?**

A: Click the **"+ Exclude App"** button in the main UI while the app is running, or add the `.exe` name to `auto_excluded_apps.txt`.

**Q: Where are my saved sessions?**

A: Click the **📂 (Folder)** icon in the top right header to open the Session Manager. You can also open the folder directly via Settings.

**Q: Does this send data online?**

A: **No personal or sensitive tracking data is ever sent online.** By default, **only the official prebuilt application releases** (compiled `.exe` or `.app` binaries) have anonymous tracking via **PostHog** enabled to help monitor active usage and app stability. If you compile or run the application from the open-source source code yourself, tracking is **completely disabled by default** (unless you explicitly set up your own local `.env` file). 

By using the prebuilt binary releases, you agree to the collection of three basic events:
- **`app_started`**: Triggered when the application is launched (includes operating system platform and version).
- **`tracking_started`**: Triggered when you start the tracking timer.
- **`tracking_stopped`**: Triggered when you stop the tracking timer (includes anonymous aggregate session duration and app counts).

All metrics are bound to a randomly generated, anonymous installation ID stored locally in your settings. No emails, billing details, names, active window titles, or keystrokes are ever captured. You can easily disable this tracking at any time by leaving the `POSTHOG_API_KEY` empty in your local `.env` file in the application directory.

**Q: Was AI Used in this Project?**

A: **Yes** Gemini <3 , Claude <3 , Deepseek <3 , QWEN <3 Thank you so much!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!


---

## 📅 Changelog

### v3.0.0 (2026.05.30)
- **Asynchronous Batch Report Generation with Pre-Aggregation**: Refactored the report processing pipeline to run fully asynchronously in background worker threads, complete with optimized SQLite database pre-aggregation.
- **Extreme Performance & Resource Optimization**: Converted the cryptographic time integrity chain to a high-performance, line-delimited JSONL format with incremental append operations and fast O(1) binary-seek loading on startup, completely eliminating disk write spikes and reducing RAM usage.
- **Streamlined Exports**: Removed legacy CSV and JSON export options in favor of clean TXT summaries and premium interactive HTML A4 invoices/reports.

---

## 📄 License

This project is licensed under the **PolyForm Noncommercial License 1.0.0**.

You are free to:
*   **Use, modify, and distribute** the software for personal, research, academic, or other private non-commercial requirements.

Under the following terms:
*   **NonCommercial** — You may not make any commercial use of the software. Commercial use is any use of the software by a business or for business purposes, or as part of a commercial service, or in any way that is intended for or directed toward commercial advantage or monetary compensation.
*   **Commercial Permission** — Custom commercial licensing or custom permission is available for businesses, sales, or partnerships by contacting the licensor.

See the [LICENSE](LICENSE.md) file for the full legal text.

---

## 🙏 Acknowledgments

*   Built with **Python** and **PyQt6**.
*   Icon extraction powered by **pywin32** and **Pillow**.
*   Process monitoring via **psutil**.
*   Vectors and icons by <a href="https://dribbble.com/saeedworks?ref=svgrepo.com" target="_blank">Saeedworks</a> in CC Attribution License via <a href="https://www.svgrepo.com/" target="_blank">SVG Repo</a>. We thank him very much for his amazing work!

### Special Thanks

We would like to express our heartfelt gratitude to the following AI assistants and teams who contributed to this project:

*   **Alibaba QWEN Coder Agentic** - For exceptional coding assistance and guidance.
*   **Google Antigravity Team** - For their innovative support and insights.
*   **Claude AI** - For valuable contributions and problem-solving expertise.

Thank you all for making True Hours possible! ❤️
