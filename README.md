# FocusLog v2.0.5

> **A lightweight, privacy-first Windows desktop time tracker with a modern Windows 11-style UI.**

FocusLog automatically monitors your active window to track productivity, calculate earnings based on hourly rates, and generate detailed session reports. It features crash recovery, auto-exclusion of system apps, and flexible export options (CSV, JSON, TXT).

![License](https://img.shields.io/badge/license-CC%20BY--NC%204.0-lightgrey.svg)
![Platform](https://img.shields.io/badge/platform-Windows-0078D4?logo=windows)
![Python](https://img.shields.io/badge/python-3.8+-3776AB?logo=python)

---

## ✨ Features

*   **🕒 Automatic Time Tracking:** Detects the foreground application and logs usage duration with second-level precision.
*   **📊 Interactive Visual Analytics Dashboard:** Custom drawn interactive PyQt6 charts (`DonutChartWidget`, `BarChartWidget`) displaying real-time live and range-filtered historical category allocation.
*   **📄 HTML Client Invoice Builder & Browser Printer:** Native dynamic invoicing profiles with Gmail-style multi-email chip token inputs, sensitive email masking (e.g., `ne**@*****.com`) for client privacy, dynamic "Unassigned" app category resolving, premium HTML templates, base64-embedded payment QR code graphics, and seamless browser-based A4 PDF printing.
*   **💰 Earnings Calculator:** Set an hourly rate to see real-time earnings accumulation during work sessions.
*   **🛡️ Smart Exclusion System:**
    *   **Auto-Exclude:** Automatically ignores system processes (Explorer, Taskbar, Search, etc.) so they don't clutter your data.
    *   **Manual Exclude:** Easily exclude specific apps (e.g., Spotify, Discord) from counting toward "Work Time."
*   **🔒 Anti-Tamper Security:** 
    *   **Monotonic Clock Protection:** Uses unchangeable system clocks to detect time manipulation
    *   **Network Time Sync:** Validates against trusted NTP servers to catch clock changes
    *   **Cryptographic Hash Chaining:** Links all entries with SHA-256 hashes to prevent retroactive editing
    *   **Trust Scoring:** Real-time integrity monitoring with tamper event logging
*   **💾 Crash Recovery:** If the app closes unexpectedly, your session is saved to an `autosave` folder and can be recovered or viewed later.
*   **📊 Detailed Reporting:**
    *   View live session stats.
    *   Export sessions to **TXT**, **JSON**, **CSV**, or premium print-ready **HTML Invoice**.
    *   Bulk export all history to a single CSV file.
*   **🎨 Modern UI:** Clean, light-themed interface inspired by Windows 11 Fluent Design, built with PyQt6.
*   **🖼️ App Icons:** Extracts and displays actual executable icons for easy visual identification.

---

## 📸 Screenshots
<div align="center">
  <strong>FocusLog Interface</strong><br>
  <em>Main Tracker, Session Report, and Dashhboard</em><br><br>
<img width="2559" height="1397" alt="FocusLog Full Window Interface" src="https://github.com/user-attachments/assets/dd4390b7-031a-46a8-84fa-39dd6ea11053"/>
  
  <br><br><br>

  <strong>Generated Invoice</strong><br>
  <em>Professional HTML invoice output</em><br><br>
<img width="2559" height="1347" alt="FocusLog HTML Invoice" src="https://github.com/user-attachments/assets/48288caf-6ab9-43eb-bd36-e303ab229450" />
</div>

---

## 🚀 Installation & Usage

### Option 1: Run from Source (Recommended for Developers)

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/yourusername/FocusLog.git
    cd FocusLog
    ```

2.  **Install Dependencies:**
    FocusLog requires `PyQt6`, `pywin32`, `psutil`, and `Pillow`.
    ```bash
    pip install PyQt6 pywin32 psutil Pillow
    ```

3.  **Run the Application:**
    You can use the provided batch file for convenience:
    ```bash
    run.bat
    ```
    *(Or manually run `python app.py`)*

### Option 2: Build Standalone Executable (.exe)

If you want to create a single `.exe` file that doesn't require Python to be installed on the target machine:

1.  **Install PyInstaller:**
    ```bash
    pip install pyinstaller
    ```

2.  **Prepare Icon (Optional):**
    Ensure you have an `icon.ico` file in the root directory. If you don't have one, you can remove the `--icon=icon.ico` flag from the build script.

3.  **Run the Build Script:**
    Double-click `build.bat` or run it in your terminal:
    ```bash
    build.bat
    ```
    *This script automatically detects your Python installation path using `%APPDATA%`, builds the executable, and cleans up temporary files.*

4.  **Find your Executable:**
    The resulting `FocusLog.exe` will be placed in the root folder.

---

## 📂 Project Structure

```text
FocusLog/
├── icon.ico            # Application Icon
├── app.py              # Main UI Entry Point (PyQt6)
├── tracker.py          # Core Logic: Polling loop, state management, crash recovery
├── report.py           # Data formatting, export utilities (CSV/JSON/TXT)
├── appinfo.py          # Windows API wrappers: Get foreground window, extract icons/names
├── config.py           # Configuration helpers: Data directory management
├── secure_time.py      # Anti-tamper security: Monotonic clocks, hash chaining, NTP sync
├── run.bat             # Quick launcher script
├── build.bat           # Automated PyInstaller build script
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── SECURITY_FEATURES.md # Detailed documentation of anti-tamper protections
```

---

## ⚙️ Configuration & Customization

FocusLog stores user data in the local app data directory:
`%LOCALAPPDATA%\FocusLog` (or `~\FocusLog` if env var is missing).

### 1. Auto-Excluded Apps
FocusLog comes with a default list of system apps to ignore (e.g., `explorer.exe`, `svchost.exe`). You can customize this list.

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

---

## 📊 Understanding the Data

### Session States
*   **Total Session Time:** The entire duration from Start to Stop/Pause.
*   **Counted Work Time:** Time spent in apps that are **not** excluded. This is the basis for earnings calculations.
*   **Excluded Apps:** Apps you have manually or automatically marked as "non-work." They appear in the report but are marked `[EXCLUDED]` and do not contribute to earnings.

### File Storage
*   **`sessions/`**: Contains manually saved session reports (`.json`).
*   **`autosave/`**: Contains automatic backups every 10 seconds (configurable) and crash recoveries.
    *   Files prefixed with `auto_`: Regular backups.
    *   Files prefixed with `recovery_`: Sessions recovered after a crash.

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
*   **`export_csv()`:** Generates a flat CSV suitable for Excel analysis.
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

A: **No.** FocusLog is 100% offline. All data is stored locally in your `%LOCALAPPDATA%` folder.

**Q: Was AI Used in this Project?**

A: **Yes** Gemini <3 , Claude <3 , Deepseek <3 , QWEN <3 Thank you so much!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!


---

## 📄 License

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International License**.

You are free to:
*   **Share** — copy and redistribute the material in any medium or format.
*   **Adapt** — remix, transform, and build upon the material.

Under the following terms:
*   **Attribution** — You must give appropriate credit, provide a link to the license, and indicate if changes were made.
*   **NonCommercial** — You may not use the material for commercial purposes.

See the [LICENSE](LICENSE.md) file for the full legal text.

---

## 🙏 Acknowledgments

*   Built with **Python** and **PyQt6**.
*   Icon extraction powered by **pywin32** and **Pillow**.
*   Process monitoring via **psutil**.
