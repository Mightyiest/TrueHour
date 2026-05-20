"""
FocusLog — Main Application UI (Tkinter).
Lightweight Windows desktop time tracker with a clean Windows 11-style light theme.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import time
import ctypes
from datetime import datetime
import json
from PIL import ImageTk
from tracker import AppTracker, AUTO_EXCLUDE_FILE
from appinfo import get_icon_image, OVERRIDES_FILE
from config import get_app_data_dir
from secure_time import get_detector
from report import (
    format_duration, format_duration_hms, build_report_data,
    export_txt, export_json, export_csv, export_csv_history,
    save_to_autosave, save_to_history, load_session_json,
)
from version import VERSION_SHORT, VERSION_FULL

# ── Force Windows to use Light Mode for this Tkinter app ──────────────
# Prevents native dialogs (filedialog, messagebox) from inheriting Dark Mode
def _force_light_mode():
    try:
        # 0=Default, 1=AllowDark, 2=ForceDark, 3=ForceLight
        ctypes.windll.uxtheme.SetPreferredAppMode(3)
        ctypes.windll.uxtheme.FlushMenuThemes()
    except Exception:
        pass

_force_light_mode()

# ── Windows 11 Fluent Light Palette ──────────────────────────────────
BG_WHITE      = "#FFFFFF"
BG_SURFACE    = "#F3F3F3"
BG_HOVER      = "#E9E9E9"
BG_CARD       = "#FBFBFB"
ACCENT        = "#0078D4"
ACCENT_HOVER  = "#106EBE"
ACCENT_LIGHT  = "#E8F1FB"
GREEN_STATUS  = "#0F7B0F"
RED_STATUS    = "#C42B1C"
ORANGE        = "#CA5010"
TEXT_PRIMARY  = "#1A1A1A"
TEXT_SECONDARY= "#616161"
TEXT_DISABLED = "#ABABAB"
BORDER        = "#E0E0E0"
BORDER_FOCUS  = "#0078D4"
CHECK_BG      = "#FFFFFF"
FONT_FAMILY   = "Segoe UI"

PROJECT_COLORS = {
    "Development": "#4F46E5",  # Indigo
    "Design": "#EC4899",       # Pink
    "Research": "#10B981",     # Emerald
    "Documentation": "#F59E0B",# Amber
    "Communication": "#06B6D4",# Cyan
    "Management": "#8B5CF6",   # Purple
    "Unassigned": "#64748B",   # Slate
}

def get_tag_color(tag_name: str) -> str:
    if tag_name in PROJECT_COLORS:
        return PROJECT_COLORS[tag_name]
    palette = list(PROJECT_COLORS.values())[:-1]
    idx = sum(ord(c) for c in tag_name) % len(palette)
    return palette[idx]

# ── Icon Path ──────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    ICON_DIR = sys._MEIPASS
else:
    ICON_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(ICON_DIR, "icon.ico")
APP_SETTINGS_FILE = os.path.join(get_app_data_dir(), "app_settings.json")

class HeaderBar(tk.Frame):
    """Modular Header Bar UI Component."""
    def __init__(self, parent, cmd_report, cmd_sessions, cmd_settings):
        super().__init__(parent, bg=BG_WHITE, height=44)
        self.grid_propagate(False)
        self.columnconfigure(1, weight=1)

        logo_frame = tk.Frame(self, bg=BG_WHITE)
        logo_frame.grid(row=0, column=0, padx=14, pady=10, sticky="w")
        tk.Label(logo_frame, text="📊 FocusLog", bg=BG_WHITE, fg=ACCENT, font=(FONT_FAMILY, 14, "bold")).pack(side="left")

        self.live_report_btn = tk.Button(self, text="📊 View Report", bg=BG_WHITE, fg=ACCENT,
                                         font=(FONT_FAMILY, 9, "bold"), bd=0, relief="flat", 
                                         cursor="hand2", command=cmd_report)
        self.live_report_btn.grid(row=0, column=2, padx=4, pady=10, sticky="e")

        self.sessions_btn = tk.Button(self, text="📂", bg=BG_WHITE, fg=TEXT_SECONDARY, 
                                      font=(FONT_FAMILY, 12), bd=0, relief="flat", 
                                      cursor="hand2", command=cmd_sessions)
        self.sessions_btn.grid(row=0, column=3, padx=4, pady=10, sticky="e")

        self.settings_btn = tk.Button(self, text="⚙", bg=BG_WHITE, fg=TEXT_SECONDARY, 
                                      font=(FONT_FAMILY, 12), bd=0, relief="flat", 
                                      cursor="hand2", command=cmd_settings)
        self.settings_btn.grid(row=0, column=4, padx=(0, 14), pady=10, sticky="e")

class FocusLogApp:
    """Main application window — Windows 11 light theme."""
    
    @property
    def live_report_btn(self): return self.header.live_report_btn
    
    @property
    def sessions_btn(self): return self.header.sessions_btn
    
    @property
    def settings_btn(self): return self.header.settings_btn

    
    def _center_window(self, win, width, height):
        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (width // 2)
        y = (win.winfo_screenheight() // 2) - (height // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
        # Force consistent light theme on all Toplevels
        win.configure(bg=BG_SURFACE)
        win.option_add("*Toplevel*background", BG_SURFACE)
        win.option_add("*Toplevel*foreground", TEXT_PRIMARY)
        win.option_add("*Button*background", BG_WHITE)
        win.option_add("*Button*activeBackground", BG_HOVER)
        win.option_add("*Button*foreground", TEXT_PRIMARY)
        win.option_add("*Label*background", BG_SURFACE)
        win.option_add("*Label*foreground", TEXT_PRIMARY)
        win.option_add("*Entry*background", BG_WHITE)
        win.option_add("*Entry*foreground", TEXT_PRIMARY)

    def __init__(self):
        self.tracker = AppTracker(poll_interval=1.0, min_track_seconds=2)
        self._load_app_settings()

        self._check_vars = {}
        self._photo_refs = []
        self._row_widgets = {}
        self._showing_placeholder = True
        
        # Performance: Track last UI update state to avoid redundant refreshes
        self._last_app_state_hash = None
        self._ui_refresh_scheduled = False

        self.root = tk.Tk()
        self.root.title("FocusLog")
        self._center_window(self.root, 440, 480)
        self.root.minsize(440, 480)
        self.root.configure(bg=BG_SURFACE)
        self.root.resizable(True, True)

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Fix native dialog text colors on Windows 11
        self.root.option_add("*Dialog*background", BG_WHITE)
        self.root.option_add("*Dialog*foreground", TEXT_PRIMARY)
        self.root.option_add("*Dialog*Button*background", BG_SURFACE)
        self.root.option_add("*Dialog*Button*foreground", TEXT_PRIMARY)
        self.root.option_add("*Dialog*Label*background", BG_WHITE)
        self.root.option_add("*Dialog*Label*foreground", TEXT_PRIMARY)

        if os.path.exists(ICON_PATH):
            try:
                self.root.iconbitmap(ICON_PATH)
            except Exception:
                pass

        self.root.bind("<<TrackerUpdate>>", lambda e: self._schedule_refresh())
        self._build_styles()
        self._build_ui()
        self._update_clock_id = None
        
        # Link tracker callback with throttling
        self.tracker.on_update = self._schedule_ui_update
        
        from tracker import ACTIVE_SESSION_FILE
        if os.path.exists(ACTIVE_SESSION_FILE):
            self.root.after(100, self._handle_interrupted_session)

    def _build_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BG_SURFACE, foreground=TEXT_PRIMARY, font=(FONT_FAMILY, 10))
        style.configure("TFrame", background=BG_SURFACE)
        style.configure("Card.TFrame", background=BG_WHITE)
        style.configure("TLabel", background=BG_SURFACE, foreground=TEXT_PRIMARY, font=(FONT_FAMILY, 10))
        style.configure("Vertical.TScrollbar", background=BG_SURFACE, troughcolor=BG_WHITE, borderwidth=0, arrowsize=0)
        style.map("Vertical.TScrollbar", background=[("active", "#C0C0C0"), ("!active", "#D0D0D0")])

        # ── Combobox Styling ──────────────────────────────────────────────
        style.configure("TCombobox", 
                        fieldbackground=BG_WHITE, 
                        background=BG_WHITE, 
                        foreground=TEXT_PRIMARY, 
                        arrowcolor=TEXT_SECONDARY, 
                        bordercolor=BORDER,
                        selectbackground=BG_HOVER,
                        selectforeground=TEXT_PRIMARY)
        style.map("TCombobox",
                  fieldbackground=[('readonly', BG_WHITE), ('active', BG_HOVER)],
                  background=[('readonly', BG_WHITE), ('active', BG_HOVER)],
                  foreground=[('readonly', TEXT_PRIMARY)])

    def _build_ui(self):
        main = tk.Frame(self.root, bg=BG_SURFACE)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)

        # ── Header Bar ──────────────────────────────────────────────
        self.header = HeaderBar(
            main, 
            cmd_report=self._show_live_report,
            cmd_sessions=self._show_session_manager,
            cmd_settings=self._show_settings
        )
        self.header.grid(row=0, column=0, sticky="ew")

        tk.Frame(main, bg=BORDER, height=1).grid(row=1, column=0, sticky="ew")

        # ── Clock + Controls Card ─────────────────────────────────────
        ctrl = tk.Frame(main, bg=BG_WHITE)
        ctrl.grid(row=2, column=0, sticky="ew", padx=12, pady=(10, 6))
        ctrl.columnconfigure(0, weight=1)

        self.clock_label = tk.Label(ctrl, text="00:00:00", bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 32, "bold"))
        self.clock_label.grid(row=0, column=0, pady=(12, 0))

        self.earnings_label = tk.Label(ctrl, text="", bg=BG_WHITE, fg=GREEN_STATUS, font=(FONT_FAMILY, 13, "bold"))
        self.earnings_label.grid(row=1, column=0, pady=(0, 4))

        self.active_label = tk.Label(ctrl, text="Ready to track", bg=BG_WHITE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9))
        self.active_label.grid(row=2, column=0, pady=(0, 8))

        btn_frame = tk.Frame(ctrl, bg=BG_WHITE)
        btn_frame.grid(row=3, column=0, pady=(0, 12))

        self.start_btn = tk.Button(btn_frame, text="▶ Start", bg=ACCENT, fg="white", activebackground=ACCENT_HOVER, activeforeground="white",
                                   font=(FONT_FAMILY, 10, "bold"), bd=0, padx=16, pady=6, cursor="hand2", relief="flat", command=self._on_start)
        self.start_btn.pack(side="left", padx=4)

        self.pause_btn = tk.Button(btn_frame, text="⏸ Pause", bg=BG_SURFACE, fg=TEXT_DISABLED, activebackground=BG_SURFACE, activeforeground=TEXT_DISABLED,
                                   font=(FONT_FAMILY, 10), bd=0, padx=16, pady=6, cursor="arrow", state="disabled", relief="flat", command=self._on_pause)
        self.pause_btn.pack(side="left", padx=4)

        self.stop_btn = tk.Button(btn_frame, text="■ Stop & Report", bg=BG_SURFACE, fg=TEXT_DISABLED, activebackground=BG_SURFACE, activeforeground=TEXT_DISABLED,
                                  font=(FONT_FAMILY, 10), bd=0, padx=16, pady=6, cursor="arrow", state="disabled", relief="flat", command=self._on_stop)
        self.stop_btn.pack(side="left", padx=4)

        # ── App List Section ──────────────────────────────────────────
        list_section = tk.Frame(main, bg=BG_SURFACE)
        list_section.grid(row=3, column=0, sticky="nsew", padx=12, pady=(4, 0))
        list_section.columnconfigure(0, weight=1)
        list_section.rowconfigure(1, weight=1)

        sec_hdr = tk.Frame(list_section, bg=BG_SURFACE)
        sec_hdr.grid(row=0, column=0, sticky="ew")
        sec_hdr.columnconfigure(1, weight=1)
        
        tk.Label(sec_hdr, text="Application usage", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9)).grid(row=0, column=0, sticky="w", padx=4, pady=(0, 4))
        exclude_btn = tk.Button(sec_hdr, text="+ Exclude App", bg=BG_SURFACE, fg=ACCENT, activebackground=BG_HOVER, activeforeground=ACCENT_HOVER,
                                font=(FONT_FAMILY, 8, "underline"), bd=0, cursor="hand2", relief="flat", command=self._on_exclude_app)
        exclude_btn.grid(row=0, column=1, sticky="e", padx=4, pady=(0, 4))

        list_card = tk.Frame(list_section, bg=BG_WHITE, bd=0, highlightthickness=1, highlightbackground=BORDER)
        list_card.grid(row=1, column=0, sticky="nsew")
        list_card.columnconfigure(0, weight=1)
        list_card.rowconfigure(0, weight=1)

        self.list_canvas = tk.Canvas(list_card, bg=BG_WHITE, bd=0, highlightthickness=0)
        self.list_scrollbar = ttk.Scrollbar(list_card, orient="vertical", command=self.list_canvas.yview)
        self.list_inner = tk.Frame(self.list_canvas, bg=BG_WHITE)
        self.list_inner.bind("<Configure>", lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self._canvas_window = self.list_canvas.create_window((0, 0), window=self.list_inner, anchor="nw")
        self.list_canvas.configure(yscrollcommand=self.list_scrollbar.set)
        self.list_canvas.bind("<Configure>", self._on_canvas_resize)
        self.list_canvas.grid(row=0, column=0, sticky="nsew")
        self.list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.list_canvas.bind("<Enter>", lambda e: self.list_canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.list_canvas.bind("<Leave>", lambda e: self.list_canvas.unbind_all("<MouseWheel>"))

        self.placeholder = tk.Label(self.list_inner, text="Click Start to begin tracking", bg=BG_WHITE, fg=TEXT_DISABLED, font=(FONT_FAMILY, 10))
        self.placeholder.pack(pady=30)

        # ── Footer ───────────────────────────────────────────────────
        footer = tk.Frame(main, bg=BG_WHITE, height=40)
        footer.grid(row=4, column=0, sticky="ew", padx=12, pady=(6, 10))
        footer.grid_propagate(False)
        footer.columnconfigure(1, weight=1)
        tk.Label(footer, text="Total work time", bg=BG_WHITE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9)).grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self.total_label = tk.Label(footer, text="0h 00m 00s", bg=BG_WHITE, fg=ACCENT, font=(FONT_FAMILY, 11, "bold"))
        self.total_label.grid(row=0, column=1, padx=12, pady=10, sticky="e")

        # ── Version Bar ──────────────────────────────────────────────
        version_bar = tk.Frame(main, bg=BG_SURFACE)
        version_bar.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 4))
        tk.Label(version_bar, text=VERSION_FULL, bg=BG_SURFACE, fg=TEXT_DISABLED, font=(FONT_FAMILY, 7)).pack(anchor="center")

        self._check_vars = {}
        self._photo_refs = []

    def _on_canvas_resize(self, event):
        self.list_canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self.list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_start(self):
        auto_name = datetime.now().strftime("Session - %I:%M %p")
        self.tracker.start(session_name=auto_name) 
        for widgets in self._row_widgets.values():
            try: widgets['row'].destroy()
            except: pass
        for w in self.list_inner.winfo_children():
            try: w.destroy()
            except: pass
        self._check_vars.clear()
        self._photo_refs.clear()
        self._row_widgets.clear()
        self._showing_placeholder = True

        self.start_btn.configure(state="disabled", bg=BG_HOVER, fg=TEXT_DISABLED, cursor="arrow")
        self.pause_btn.configure(state="normal", bg=BG_SURFACE, fg=TEXT_PRIMARY, cursor="hand2", text="⏸ Pause")
        self.stop_btn.configure(state="normal", bg=RED_STATUS, fg="white", cursor="hand2")
        if self.hourly_rate > 0:
            self.earnings_label.configure(text=f"💰 {self.currency_symbol}0.00 earned", fg=GREEN_STATUS)
        self._tick_clock()

    def _on_stop(self):
        self.tracker.stop()
        if self._update_clock_id:
            self.root.after_cancel(self._update_clock_id) 
            self._update_clock_id = None
        self.start_btn.configure(state="normal", bg=ACCENT, fg="white", cursor="hand2")
        self.pause_btn.configure(state="disabled", bg=BG_SURFACE, fg=TEXT_DISABLED, cursor="arrow")
        self.stop_btn.configure(state="disabled", bg=BG_SURFACE, fg=TEXT_DISABLED, cursor="arrow")
        self.active_label.configure(text="Session ended", fg=TEXT_SECONDARY)
        self.clock_label.configure(text="00:00:00")
        self.earnings_label.configure(text="")
        self.root.title("FocusLog")

        report = build_report_data(self.tracker, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol)
        try:
            save_to_autosave(report)
        except Exception as e:
            print(f"[FocusLog] Stop autosave failed: {e}")
        self._show_report(report, is_new=True)

    def _show_live_report(self):
        if not self.tracker.running:
            messagebox.showinfo("No Active Session", "Start tracking first to view a live report.")
            return
        if hasattr(self, '_live_report_window') and self._live_report_window and self._live_report_window.winfo_exists(): 
            self._live_report_window.lift()
            self._live_report_window.focus_force()
            return
        report = build_report_data(self.tracker, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol)
        self._show_report(report, is_new=False, is_live=True)

    def _on_pause(self):
        is_paused = self.tracker.toggle_pause()
        if is_paused:
            self.pause_btn.configure(text="▶ Resume", bg=ACCENT_LIGHT, fg=ACCENT)
            self.active_label.configure(text="⏸ Session paused", fg=ORANGE)
        else:
            self.pause_btn.configure(text="⏸ Pause", bg=BG_SURFACE, fg=TEXT_PRIMARY)
            self.active_label.configure(text=f"Active: {self.tracker.get_current_app()}", fg=TEXT_SECONDARY)

    def _on_exclude_app(self):
        win = tk.Toplevel(self.root)
        win.configure(bg=BG_SURFACE)
        win.option_add("*background", BG_SURFACE)
        win.option_add("*foreground", TEXT_PRIMARY)
        win.title("Exclude Application")
        self._center_window(win, 380, 440)
        win.configure(bg=BG_SURFACE)
        win.transient(self.root)
        win.grab_set()
        if os.path.exists(ICON_PATH):
            try: win.iconbitmap(ICON_PATH)
            except: pass

        tk.Label(win, text="Select a running application to exclude:", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9)).pack(pady=(12, 4), padx=14, anchor="w")
        list_frame = tk.Frame(win, bg=BG_WHITE, bd=0, highlightthickness=1, highlightbackground=BORDER)
        list_frame.pack(fill="both", expand=True, padx=14, pady=4)
        canvas = tk.Canvas(list_frame, bg=BG_WHITE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_WHITE)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_win, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        from appinfo import get_running_applications, get_icon_image
        running_apps = get_running_applications()
        win.photo_refs = []
        
        def _exclude_and_close(friendly, exe_path):
            self.tracker.set_included(friendly, False)
            if exe_path: self.tracker.app_exe_paths[friendly] = exe_path
            if friendly not in self.tracker.app_times: self.tracker.app_times[friendly] = 0
            self._refresh_app_list()
            win.destroy()

        def _browse_file():
            path = filedialog.askopenfilename(filetypes=[("Executable files", "*.exe"), ("All files", "*.*")])
            if path:
                base = os.path.basename(path)
                if base.lower().endswith(".exe"): base = base[:-4]
                from appinfo import resolve_name
                friendly = resolve_name(path, base)
                _exclude_and_close(friendly, path)

        # Mousewheel scrolling
        def _on_mousewheel_dialog(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel_dialog))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        for i, (friendly, exe_path) in enumerate(running_apps):
            row_bg = BG_WHITE if i % 2 == 0 else BG_SURFACE
            row = tk.Frame(inner, bg=row_bg)
            row.pack(fill="x")
            icon_img = get_icon_image(exe_path, size=16) if exe_path else None
            if icon_img:
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(icon_img)
                win.photo_refs.append(photo)
                icon_lbl = tk.Label(row, image=photo, bg=row_bg)
                icon_lbl.pack(side="left", padx=8, pady=4)
            else:
                tk.Frame(row, bg=row_bg, width=32).pack(side="left", pady=4)
            btn = tk.Button(row, text=friendly, bg=row_bg, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9), relief="flat", anchor="w", bd=0, command=lambda f=friendly, p=exe_path: _exclude_and_close(f, p))
            btn.pack(side="left", fill="x", expand=True, pady=4)
        tk.Button(win, text="Browse for .exe...", bg=BG_SURFACE, fg=ACCENT, activebackground=BG_HOVER, activeforeground=ACCENT_HOVER, font=(FONT_FAMILY, 9, "underline"), bd=0, cursor="hand2", relief="flat", 
                  command=_browse_file).pack(pady=(6, 12))

    def _on_closing(self):
        if self.confirm_on_close:
            msg = "A tracking session is active.\nAre you sure you want to stop tracking and exit?" if self.tracker.running else "Are you sure you want to close FocusLog?"
            if not messagebox.askyesno("Confirm Exit", msg):
                return
        if self.tracker.running:
            self.tracker.stop()
            try:
                report = build_report_data(self.tracker, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol)
                save_to_autosave(report)
            except Exception as e:
                print(f"[FocusLog] Closing autosave failed: {e}")
        self.root.destroy()

    def _get_relative_time(self, timestamp):
        diff = time.time() - timestamp
        if diff < 60: return "Just now"
        if diff < 3600: return f"{int(diff/60)}m ago"
        if diff < 86400: return f"{int(diff/3600)}h ago"
        return datetime.fromtimestamp(timestamp).strftime("%b %d, %Y")

    def _handle_interrupted_session(self):
        from tracker import ACTIVE_SESSION_FILE, AppTracker
        temp_tracker = AppTracker()
        if temp_tracker.load_crash_data():
            report = build_report_data(temp_tracker, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol)
            try:
                save_to_autosave(report)
                if os.path.exists(ACTIVE_SESSION_FILE):
                    os.remove(ACTIVE_SESSION_FILE)
                messagebox.showinfo("Session Recovered", "An interrupted session was found and saved as a recovery backup.\n\nYou can view or resume it from the Recoveries tab.")
                self._show_session_manager()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save interrupted session: {e}")
        else:
            if os.path.exists(ACTIVE_SESSION_FILE):
                try: os.remove(ACTIVE_SESSION_FILE)
                except: pass

    def _show_session_manager(self):
        win = tk.Toplevel(self.root)
        win.configure(bg=BG_SURFACE)
        win.option_add("*background", BG_SURFACE)
        win.option_add("*foreground", TEXT_PRIMARY)
        win.title("Session Manager")
        self._center_window(win, 480, 540)
        win.configure(bg=BG_SURFACE)
        win.transient(self.root)
        if os.path.exists(ICON_PATH):
            try: win.iconbitmap(ICON_PATH)
            except: pass

        history_folder = os.path.join(get_app_data_dir(), "sessions")
        autosave_folder = os.path.join(get_app_data_dir(), "autosave")
        os.makedirs(history_folder, exist_ok=True)
        os.makedirs(autosave_folder, exist_ok=True)

        tab_frame = tk.Frame(win, bg=BG_SURFACE)
        tab_frame.pack(fill="x", padx=14, pady=(0, 10))
        sessions_tab = tk.Button(tab_frame, text="Sessions", bg=BG_WHITE, fg=ACCENT, font=(FONT_FAMILY, 9, "bold"), relief="flat", padx=15, pady=5)
        sessions_tab.pack(side="left", padx=(0, 4))
        recoveries_tab = tk.Button(tab_frame, text="Recoveries", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9), relief="flat", padx=15, pady=5)
        recoveries_tab.pack(side="left")
        tk.Button(tab_frame, text="Open Folder", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 8, "underline"), bd=0, cursor="hand2", 
                  command=lambda: os.startfile(autosave_folder if recoveries_tab.cget("bg") == BG_WHITE else history_folder)).pack(side="right", pady=5)

        list_frame = tk.Frame(win, bg=BG_SURFACE)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        canvas = tk.Canvas(list_frame, bg=BG_WHITE, highlightthickness=1, highlightbackground=BORDER)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_WHITE)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_win, width=e.width))

        import glob
        def _render_list(show_recoveries=False):
            for widget in inner.winfo_children():
                widget.destroy()
            target_folder = autosave_folder if show_recoveries else history_folder
            if show_recoveries:
                recoveries_tab.configure(bg=BG_WHITE, fg=ACCENT, font=(FONT_FAMILY, 9, "bold"))
                sessions_tab.configure(bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9))
            else:
                sessions_tab.configure(bg=BG_WHITE, fg=ACCENT, font=(FONT_FAMILY, 9, "bold"))
                recoveries_tab.configure(bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9))
            files = glob.glob(os.path.join(target_folder, "*.json"))
            files.sort(key=os.path.getmtime, reverse=True)
            if not files:
                label = "No manual sessions found." if not show_recoveries else "No auto-saves/recoveries found."
                tk.Label(inner, text=label, bg=BG_WHITE, fg=TEXT_DISABLED, font=(FONT_FAMILY, 10)).pack(pady=40, padx=20)
                return

            for i, filepath in enumerate(files):
                filename = os.path.basename(filepath)
                mtime = os.path.getmtime(filepath)
                rel_time = self._get_relative_time(mtime)
                bg_color = BG_WHITE if i % 2 == 0 else BG_SURFACE
                row = tk.Frame(inner, bg=bg_color)
                row.pack(fill="x")
                title_frame = tk.Frame(row, bg=bg_color)
                title_frame.pack(side="left", fill="x", expand=True, padx=8, pady=8)
                try:
                    with open(filepath, "r", encoding="utf-8") as _f:
                        _data = json.load(_f)
                    session_name = _data.get("session_name", "").strip()
                    date_str = _data.get("date", "")
                except:
                    session_name = ""
                    date_str = filename.replace("session_", "").replace("auto_", "").replace("recovery_", "").replace(".json", "").replace("_", "  ")
                name_lbl = tk.Label(title_frame, text=session_name or "Unnamed", bg=bg_color, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9, "bold"), anchor="w")
                name_lbl.pack(side="top", fill="x")
                date_lbl = tk.Label(title_frame, text=date_str, bg=bg_color, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 8), anchor="w")
                date_lbl.pack(side="top", fill="x")
                tag_bg = "#E1F5FE" if i == 0 else "#F5F5F5"
                tag_fg = "#0288D1" if i == 0 else TEXT_SECONDARY
                tag_txt = "Latest" if i == 0 else rel_time
                tag_frame = tk.Frame(title_frame, bg=tag_bg, padx=6)
                tag_frame.pack(side="left", pady=(2, 0))
                tk.Label(tag_frame, text=tag_txt, bg=tag_bg, fg=tag_fg, font=(FONT_FAMILY, 7, "bold")).pack()
                btn_frame = tk.Frame(row, bg=bg_color)
                btn_frame.pack(side="right", padx=8, pady=8)
                def _open_report_local(p=filepath):
                    try:
                        rep = load_session_json(p)
                        self._show_report(rep, is_new=False)
                    except Exception as e:
                        messagebox.showerror("Error", f"Could not load: {e}", parent=win)
                def _resume_from_file(p=filepath):
                    if self.tracker.running:
                        if not messagebox.askyesno("Active Session", "A session is currently running.\nStop it and resume this one?", parent=win):
                            return
                        self._on_stop()
                    self._resume_session(p)
                    win.destroy()
                tk.Button(btn_frame, text="▶ Resume", bg=ACCENT, fg="white", font=(FONT_FAMILY, 8, "bold"), relief="flat", bd=0, padx=6, cursor="hand2", command=_resume_from_file).pack(side="left", padx=2)
                tk.Button(btn_frame, text="View", bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 8), relief="solid", bd=1, cursor="hand2", command=_open_report_local).pack(side="left", padx=2)

                def _on_enter(e, r=row, bf=btn_frame, tf=title_frame, nl=name_lbl, dl=date_lbl):
                    r.configure(bg=BG_HOVER); bf.configure(bg=BG_HOVER); tf.configure(bg=BG_HOVER); nl.configure(bg=BG_HOVER); dl.configure(bg=BG_HOVER)
                def _on_leave(e, r=row, c=bg_color, bf=btn_frame, tf=title_frame, nl=name_lbl, dl=date_lbl):
                    r.configure(bg=c); bf.configure(bg=c); tf.configure(bg=c); nl.configure(bg=c); dl.configure(bg=c)
                row.bind("<Enter>", _on_enter)
                row.bind("<Leave>", _on_leave)

        sessions_tab.configure(command=lambda: _render_list(False))
        recoveries_tab.configure(command=lambda: _render_list(True))
        _render_list(False)

        footer = tk.Frame(win, bg=BG_SURFACE)
        footer.pack(fill="x", padx=14, pady=(0, 14))
        tk.Button(footer, text="📊 Export All to CSV", bg=ACCENT, fg="white", font=(FONT_FAMILY, 9, "bold"), relief="flat", bd=0, padx=12, pady=6, cursor="hand2", command=self._export_csv_history).pack(side="left")
        tk.Button(footer, text="Close", bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9), relief="solid", bd=1, padx=12, pady=5, cursor="hand2", command=win.destroy).pack(side="right")

    def _resume_session(self, filepath):
        """Resume tracking from a saved session JSON file."""
        try:
            # Cancel any existing clock ticker to prevent duplicate loops
            if self._update_clock_id:
                self.root.after_cancel(self._update_clock_id)
                self._update_clock_id = None

            # Clear existing UI state
            for widgets in self._row_widgets.values():
                try: widgets['row'].destroy()
                except: pass
            for w in self.list_inner.winfo_children():
                try: w.destroy()
                except: pass
            self._check_vars.clear()
            self._photo_refs.clear()
            self._row_widgets.clear()
            self._showing_placeholder = True
            self._last_app_state_hash = None

            if not self.tracker.load_from_report(filepath):
                messagebox.showerror("Error", "Failed to resume session. The file may be corrupted.")
                return

            # Update UI to reflect running state
            self.start_btn.configure(state="disabled", bg=BG_HOVER, fg=TEXT_DISABLED, cursor="arrow")
            self.pause_btn.configure(state="normal", bg=BG_SURFACE, fg=TEXT_PRIMARY, cursor="hand2", text="⏸ Pause")
            self.stop_btn.configure(state="normal", bg=RED_STATUS, fg="white", cursor="hand2")
            if self.hourly_rate > 0:
                self.earnings_label.configure(text=f"💰 {self.currency_symbol}0.00 earned", fg=GREEN_STATUS)
            self.active_label.configure(text=f"▶ Resumed: {self.tracker.session_name}", fg=GREEN_STATUS)
            self._tick_clock()
            self._refresh_app_list()
            messagebox.showinfo("Session Resumed", f"Resumed session: {self.tracker.session_name}\nTracking is now active.")
        except Exception as e:
            messagebox.showerror("Resume Error", f"Could not resume session:\n{e}")

    def _load_app_settings(self):
        self.confirm_on_close = True
        self.min_track_seconds = 2
        self.auto_save_seconds = 10
        self.currency_symbol = "$"
        self.hourly_rate = 0.0
        if os.path.exists(APP_SETTINGS_FILE):
            try:
                with open(APP_SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    self.confirm_on_close = data.get("confirm_on_close", True)
                    self.min_track_seconds = data.get("min_track_seconds", 2)
                    self.auto_save_seconds = data.get("auto_save_seconds", 10)
                    raw_curr = data.get("currency_symbol", "$")
                    self.currency_symbol = str(raw_curr).split()[0].split('(')[0].strip() if raw_curr else "$"
                    self.hourly_rate = float(data.get("hourly_rate", 0.0))
                    self.tracker.min_track_seconds = self.min_track_seconds
                    self.tracker.save_interval = self.auto_save_seconds
            except (json.JSONDecodeError, ValueError, OSError) as e:
                print(f"[FocusLog] Failed to load app settings: {e}")

    def _save_app_settings(self):
        try:
            dirpath = os.path.dirname(APP_SETTINGS_FILE)
            if dirpath: os.makedirs(dirpath, exist_ok=True)
            with open(APP_SETTINGS_FILE, "w") as f:
                json.dump({"confirm_on_close": self.confirm_on_close, "min_track_seconds": self.min_track_seconds, "auto_save_seconds": self.auto_save_seconds, "currency_symbol": self.currency_symbol, "hourly_rate": self.hourly_rate}, f)
        except (ValueError, OSError) as e:
            print(f"[FocusLog] Failed to save app settings: {e}")

    def _show_settings(self):
        win = tk.Toplevel(self.root)
        win.configure(bg=BG_SURFACE)
        win.option_add("*background", BG_SURFACE)
        win.option_add("*foreground", TEXT_PRIMARY)
        win.title("Settings")
        self._center_window(win, 360, 600)  # Increased height for config files and categories
        win.configure(bg=BG_SURFACE)
        win.transient(self.root)
        win.grab_set()
        if os.path.exists(ICON_PATH):
            try: win.iconbitmap(ICON_PATH)
            except: pass

        tk.Label(win, text="Settings", bg=BG_SURFACE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=14, pady=(12, 8))
        
        # Confirm on close
        confirm_var = tk.IntVar(value=1 if self.confirm_on_close else 0)
        tk.Checkbutton(win, text="Always ask for confirmation before closing", variable=confirm_var, bg=BG_SURFACE, activebackground=BG_SURFACE, highlightthickness=0, 
                       command=lambda: setattr(self, 'confirm_on_close', bool(confirm_var.get())) or self._save_app_settings()).pack(anchor="w", padx=14, pady=4)
        
        # Min activity threshold
        tk.Label(win, text="Min activity threshold (seconds):", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9)).pack(anchor="w", padx=14, pady=(10, 2))
        min_sec_entry = tk.Entry(win, bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 10), bd=0, highlightthickness=1, highlightbackground=BORDER)
        min_sec_entry.pack(fill="x", padx=14, pady=2)
        min_sec_entry.insert(0, str(self.min_track_seconds))
        
        # Auto-save interval
        tk.Label(win, text="Auto-save interval (seconds):", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9)).pack(anchor="w", padx=14, pady=(10, 2))
        auto_save_entry = tk.Entry(win, bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 10), bd=0, highlightthickness=1, highlightbackground=BORDER)
        auto_save_entry.pack(fill="x", padx=14, pady=2)
        auto_save_entry.insert(0, str(self.auto_save_seconds))

        # Billing Section
        tk.Label(win, text="Billing", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", padx=14, pady=(16, 2))
        rate_frame = tk.Frame(win, bg=BG_SURFACE)
        rate_frame.pack(fill="x", padx=14, pady=2)
        tk.Label(rate_frame, text="Currency symbol:", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9)).pack(side="left")
        tk.Label(rate_frame, text="Hourly rate:", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9)).pack(side="right")
        
        rate_input_frame = tk.Frame(win, bg=BG_SURFACE)
        rate_input_frame.pack(fill="x", padx=14, pady=2)

        # ── Currency Dropdown with Acronyms ───────────────────────────────
        currency_options = [
            "$ (USD)", "€ (EUR)", "£ (GBP)", "¥ (JPY/CNY)", "₱ (PHP)", "₹ (INR)", 
            "₽ (RUB)", "₩ (KRW)", "₫ (VND)", "฿ (THB)", "₪ (ILS)", "₺ (TRY)", 
            "Rp (IDR)", "RM (MYR)", "R$ (BRL)", "C$ (CAD)", "A$ (AUD)", "S$ (SGD)", 
            "NZ$ (NZD)", "CHF (CHF)", "kr (SEK/NOK)", "zł (PLN)", "Kč (CZK)", 
            "Ft (HUF)", "lei (RON)", "лв (BGN)", "₴ (UAH)", "R (ZAR)"
        ]
        self.currency_var = tk.StringVar(value=self.currency_symbol)
        curr_combo = ttk.Combobox(
            rate_input_frame, 
            textvariable=self.currency_var, 
            values=currency_options, 
            width=12, 
            state="readonly", 
            font=(FONT_FAMILY, 10)
        )
        curr_combo.pack(side="left", padx=(0, 6))
        # Set default selection safely
        matched = [c for c in currency_options if c.startswith(self.currency_symbol)]
        curr_combo.set(matched[0] if matched else self.currency_symbol)

        # ── Hourly Rate Entry ─────────────────────────────────────────────
        rate_entry = tk.Entry(
            rate_input_frame, 
            bg=BG_WHITE, fg=TEXT_PRIMARY, 
            font=(FONT_FAMILY, 10), bd=0, 
            highlightthickness=1, highlightbackground=BORDER
        )
        rate_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        rate_entry.insert(0, f"{self.hourly_rate:.2f}")

        # ── Feedback Label ────────────────────────────────────────────────
        save_feedback_lbl = tk.Label(
            rate_input_frame, text="", bg=BG_SURFACE, 
            fg=GREEN_STATUS, font=(FONT_FAMILY, 9, "bold")
        )
        save_feedback_lbl.pack(side="right", padx=(4, 0))

        # ── Unified Save Function ─────────────────────────────────────────
        def _save_currency_and_rate():
            try:
                raw_symbol = self.currency_var.get().strip()
                self.currency_symbol = raw_symbol.split()[0].split('(')[0].strip() if raw_symbol else "$"
                self.hourly_rate = float(rate_entry.get().strip() or 0)
                self._save_app_settings()

                # Update live earnings immediately if tracking
                if self.tracker.running and self.hourly_rate > 0:
                    counted = self.tracker.get_counted_seconds()
                    earned = (counted / 3600) * self.hourly_rate
                    state_text = " (paused)" if self.tracker.paused else ""
                    self.earnings_label.configure(
                        text=f"💰 {self.currency_symbol}{earned:,.2f} earned{state_text}",
                        fg=GREEN_STATUS if not self.tracker.paused else TEXT_SECONDARY
                    )

                save_feedback_lbl.configure(text="Set!", fg=GREEN_STATUS)
                win.after(2000, lambda: save_feedback_lbl.configure(text=""))
            except ValueError:
                save_feedback_lbl.configure(text="Invalid", fg=RED_STATUS)
                win.after(2000, lambda: save_feedback_lbl.configure(text=""))

        # ── Save Button ───────────────────────────────────────────────────
        save_curr_btn = tk.Button(
            rate_input_frame, text="💾", 
            bg=BG_WHITE, fg=ACCENT, 
            activebackground=BG_HOVER, activeforeground=ACCENT,
            font=(FONT_FAMILY, 11), bd=0, 
            highlightthickness=1, highlightbackground=BORDER,
            cursor="hand2", relief="flat", 
            command=_save_currency_and_rate
        )
        save_curr_btn.pack(side="right", padx=(0, 4))

        # ── Configuration Files (RESTORED) ──────────────────────────────
        tk.Label(win, text="Configuration Files", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", padx=14, pady=(16, 4))
        
        def _open_file(filepath):
            if not os.path.exists(filepath):
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write("# Configuration file created.\n")
                except Exception: pass
            try: os.startfile(filepath)
            except Exception: messagebox.showerror("Error", f"Could not open: {filepath}")

        tk.Button(win, text="Edit Name Overrides", bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9), bd=1, relief="solid", cursor="hand2", 
                  command=lambda: _open_file(OVERRIDES_FILE)).pack(fill="x", padx=14, pady=4)
        
        excl_row = tk.Frame(win, bg=BG_SURFACE)
        excl_row.pack(fill="x", padx=14, pady=(4, 0))
        
        tk.Button(excl_row, text="Edit Auto-Exclusions", bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9), bd=1, relief="solid", cursor="hand2", 
                  command=lambda: _open_file(AUTO_EXCLUDE_FILE)).pack(side="left", fill="x", expand=True)
        
        reload_lbl = tk.Label(excl_row, text=" ", bg=BG_SURFACE, fg=GREEN_STATUS, font=(FONT_FAMILY, 9))
        
        def _reload_exclusions():
            from tracker import reload_auto_excluded
            lock = self.tracker._lock if self.tracker.running else None
            success = reload_auto_excluded(lock=lock)
            if success: reload_lbl.configure(text="✓ Reloaded", fg=GREEN_STATUS)
            else: reload_lbl.configure(text="✗ Failed", fg=RED_STATUS)
            win.after(2000, lambda: reload_lbl.configure(text=" "))

        tk.Button(excl_row, text="🔄 Reload", bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9), bd=1, relief="solid", cursor="hand2", 
                  command=_reload_exclusions).pack(side="left", padx=(4, 0))
        reload_lbl.pack(side="left", padx=8)

        # Categories Button
        tk.Button(win, text="Manage Project Categories", bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9, "bold"), bd=1, relief="solid", cursor="hand2", 
                  command=self._show_categories_dialog).pack(fill="x", padx=14, pady=10)

        # Save/Cancel Buttons
        btn_frame = tk.Frame(win, bg=BG_SURFACE)
        btn_frame.pack(fill="x", side="bottom", pady=14, padx=14)
        
        def save_and_close():
            try:
                self.min_track_seconds = int(min_sec_entry.get())
                self.auto_save_seconds = int(auto_save_entry.get())
                raw_symbol = self.currency_var.get().strip()
                self.currency_symbol = raw_symbol.split()[0].split('(')[0].strip() if raw_symbol else "$"
                self.hourly_rate = float(rate_entry.get().strip() or 0)
                self.tracker.min_track_seconds = self.min_track_seconds
                self.tracker.save_interval = self.auto_save_seconds
                self._save_app_settings()
                win.destroy()
            except ValueError:
                messagebox.showerror("Error", "Please enter valid numeric values.")

        tk.Button(btn_frame, text="Save Settings", bg=ACCENT, fg="white", font=(FONT_FAMILY, 9, "bold"), bd=0, padx=16, pady=8, cursor="hand2", 
                  command=save_and_close).pack(side="right")
        tk.Button(btn_frame, text="Cancel", bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9), relief="solid", bd=1, padx=16, pady=7, cursor="hand2", 
                  command=win.destroy).pack(side="right", padx=8)

    def _tick_clock(self):
        if not self.tracker.running: return
        elapsed = self.tracker.get_elapsed()
        self.clock_label.configure(text=format_duration_hms(elapsed))
        if self.hourly_rate > 0:
            counted = self.tracker.get_counted_seconds()
            earned = (counted / 3600) * self.hourly_rate
            display_symbol = self.currency_symbol.split()[0].split('(')[0].strip() if self.currency_symbol else "$"
            if self.tracker.paused:
                self.earnings_label.configure(text=f"💰 {display_symbol}{earned:,.2f} earned (paused)", fg=TEXT_SECONDARY)
            else:
                self.earnings_label.configure(text=f"💰 {display_symbol}{earned:,.2f} earned", fg=GREEN_STATUS)
        else:
            self.earnings_label.configure(text="")
        if not self.tracker.paused:
            current = self.tracker.get_current_app()
            self.active_label.configure(text=f"Active: {current}" if current else " ")
        self._update_ui_naming()
        self._update_clock_id = self.root.after(250, self._tick_clock)

    def _update_ui_naming(self):
        name = getattr(self.tracker, "session_name", "")
        self.root.title(f"FocusLog | {name}" if name else "FocusLog")

    def _schedule_ui_update(self):
        """Schedule a UI update with throttling to avoid excessive refreshes."""
        if self._ui_refresh_scheduled:
            return
        self._ui_refresh_scheduled = True
        try:
            self.root.event_generate("<<TrackerUpdate>>", when="tail")
        except Exception:
            self._ui_refresh_scheduled = False

    def _schedule_refresh(self):
        """Called by the <<TrackerUpdate>> virtual event — triggers the actual UI refresh."""
        self._refresh_app_list()

    def _show_tag_menu(self, event, app_name):
        menu = tk.Menu(self.root, tearoff=0)
        projects = self.tracker.tag_manager.projects
        
        for proj in projects:
            current_tag = self.tracker.get_app_tag(app_name)
            label = f"✓ {proj}" if proj == current_tag else proj
            menu.add_command(
                label=label,
                command=lambda p=proj, a=app_name: self._set_app_tag_and_refresh(a, p)
            )
            
        menu.add_separator()
        menu.add_command(label="Manage Categories...", command=self._show_categories_dialog)
        
        menu.post(event.x_root, event.y_root)

    def _set_app_tag_and_refresh(self, app_name, tag):
        self.tracker.set_app_tag(app_name, tag)
        self._last_app_state_hash = None
        self._refresh_app_list()

    def _show_categories_dialog(self):
        win = tk.Toplevel(self.root)
        win.configure(bg=BG_SURFACE)
        win.option_add("*background", BG_SURFACE)
        win.option_add("*foreground", TEXT_PRIMARY)
        win.title("Manage Categories")
        self._center_window(win, 360, 440)
        win.transient(self.root)
        win.grab_set()
        if os.path.exists(ICON_PATH):
            try: win.iconbitmap(ICON_PATH)
            except: pass

        tk.Label(win, text="Manage Categories", bg=BG_SURFACE, fg=TEXT_PRIMARY, 
                 font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=14, pady=(12, 8))

        list_frame = tk.Frame(win, bg=BG_WHITE, bd=1, relief="solid")
        list_frame.pack(fill="both", expand=True, padx=14, pady=8)
        
        list_inner = tk.Frame(list_frame, bg=BG_WHITE)
        list_inner.pack(fill="both", expand=True, padx=2, pady=2)
        
        def refresh_categories_list():
            for w in list_inner.winfo_children():
                w.destroy()
            
            projects = self.tracker.tag_manager.projects
            for idx, proj in enumerate(projects):
                row = tk.Frame(list_inner, bg=BG_WHITE)
                row.pack(fill="x", ipady=4, padx=6)
                
                color = get_tag_color(proj)
                dot = tk.Label(row, text="●", bg=BG_WHITE, fg=color, font=(FONT_FAMILY, 12))
                dot.pack(side="left", padx=(4, 6))
                
                lbl = tk.Label(row, text=proj, bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 10))
                lbl.pack(side="left")
                
                if proj != "Unassigned":
                    del_btn = tk.Button(row, text="❌", bg=BG_WHITE, fg=RED_STATUS, 
                                        font=(FONT_FAMILY, 8), bd=0, cursor="hand2", relief="flat",
                                        command=lambda p=proj: delete_project(p))
                    del_btn.pack(side="right", padx=4)
                    
        def delete_project(project):
            if self.tracker.tag_manager.remove_project(project):
                self._last_app_state_hash = None
                self._refresh_app_list()
                refresh_categories_list()
                
        add_frame = tk.Frame(win, bg=BG_SURFACE)
        add_frame.pack(fill="x", padx=14, pady=(8, 14))
        
        entry = tk.Entry(add_frame, bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 10), 
                         bd=0, highlightthickness=1, highlightbackground=BORDER)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=3)
        
        def add_project():
            name = entry.get().strip()
            if not name:
                return
            if name in self.tracker.tag_manager.projects:
                messagebox.showerror("Error", f"Category '{name}' already exists.")
                return
            if self.tracker.tag_manager.add_project(name):
                entry.delete(0, tk.END)
                refresh_categories_list()
                self._last_app_state_hash = None
                self._refresh_app_list()
                
        tk.Button(add_frame, text="Add Category", bg=ACCENT, fg="white", 
                  font=(FONT_FAMILY, 9, "bold"), bd=0, padx=12, pady=4, cursor="hand2",
                  command=add_project).pack(side="right")
                  
        refresh_categories_list()

    def _refresh_app_list(self):
        """Refresh the app list UI only if data has changed significantly."""
        try:
            apps = self.tracker.get_app_times_sorted()
            
            # Create a hashable state key for change detection (excluding time values for efficiency)
            app_state_key = tuple((name, included) for name, _, included in apps)
            
            # Skip refresh if app list structure hasn't changed (same apps, same inclusion status)
            if app_state_key == self._last_app_state_hash and not self._showing_placeholder:
                # Only update the total time without rebuilding the entire list
                counted = self.tracker.get_counted_seconds()
                self.total_label.configure(text=format_duration(counted))
                self._ui_refresh_scheduled = False
                return
            
            self._last_app_state_hash = app_state_key
            self._ui_refresh_scheduled = False
            
            if not apps:
                for w in self.list_inner.winfo_children():
                    w.destroy()
                self._row_widgets.clear()
                tk.Label(self.list_inner, text="Waiting for app activity...", bg=BG_WHITE, fg=TEXT_DISABLED, font=(FONT_FAMILY, 10)).pack(pady=20)
                self._showing_placeholder = True
                return
                
            if self._showing_placeholder:
                for w in self.list_inner.winfo_children():
                    w.destroy()
                self._showing_placeholder = False
                
            new_photo_refs = []
            active_apps = set()
            
            for i, (app_name, secs, included) in enumerate(apps):
                active_apps.add(app_name)
                row_bg = BG_WHITE if i % 2 == 0 else BG_SURFACE
                
                if app_name not in self._check_vars:
                    var = tk.IntVar(value=1 if included else 0)
                    self._check_vars[app_name] = var
                else:
                    var = self._check_vars[app_name]
                    if var.get() != (1 if included else 0):
                        var.set(1 if included else 0)
                        
                is_included = bool(var.get())
                fg = TEXT_PRIMARY if is_included else TEXT_DISABLED
                time_fg = TEXT_SECONDARY if is_included else TEXT_DISABLED
                
                if app_name not in self._row_widgets:
                    # Create new row
                    row = tk.Frame(self.list_inner, bg=row_bg)
                    row.pack(fill="x", ipady=3)
                    row.columnconfigure(2, weight=1)
                    
                    cb = tk.Checkbutton(row, variable=var, bg=row_bg, activebackground=row_bg, 
                                       selectcolor=CHECK_BG, bd=0, highlightthickness=0, 
                                       onvalue=1, offvalue=0, 
                                       command=lambda n=app_name, v=var: self._toggle_include(n, v))
                    cb.grid(row=0, column=0, padx=(8, 2), pady=2)
                    
                    exe_path = self.tracker.get_exe_path(app_name)
                    icon_img = get_icon_image(exe_path, size=16) if exe_path else None
                    icon_lbl = None
                    
                    if icon_img:
                        photo = ImageTk.PhotoImage(icon_img)
                        new_photo_refs.append(photo)
                        icon_lbl = tk.Label(row, image=photo, bg=row_bg, bd=0)
                        icon_lbl.grid(row=0, column=1, padx=(2, 4), pady=2)
                        icon_lbl._photo = photo
                    else:
                        tk.Frame(row, bg=row_bg, width=20).grid(row=0, column=1)
                        
                    name_lbl = tk.Label(row, text=app_name, bg=row_bg, fg=fg, 
                                       font=(FONT_FAMILY, 10), anchor="w")
                    name_lbl.grid(row=0, column=2, sticky="ew", padx=(2, 4))
                    
                    tag = self.tracker.get_app_tag(app_name)
                    tag_bg = get_tag_color(tag)
                    tag_lbl = tk.Label(row, text=tag, bg=tag_bg, fg="#FFFFFF",
                                       font=(FONT_FAMILY, 7, "bold"), padx=6, pady=1,
                                       cursor="hand2", relief="flat")
                    tag_lbl.grid(row=0, column=3, padx=(4, 4), pady=2)
                    tag_lbl.bind("<Button-1>", lambda e, a=app_name: self._show_tag_menu(e, a))
                    
                    time_lbl = tk.Label(row, text=format_duration(secs), bg=row_bg, fg=time_fg, 
                                       font=(FONT_FAMILY, 10), anchor="e")
                    time_lbl.grid(row=0, column=4, sticky="e", padx=(4, 12))
                    
                    self._row_widgets[app_name] = {
                        'row': row, 'cb': cb, 'name': name_lbl, 'tag': tag_lbl, 'time': time_lbl, 'icon': icon_lbl
                    }
                else:
                    # Update existing row - optimized path
                    widgets = self._row_widgets[app_name]
                    # Only update if visual properties changed
                    if widgets['time'].cget('text') != format_duration(secs):
                        widgets['time'].configure(text=format_duration(secs))
                    
                    # Update tag badge if changed
                    tag = self.tracker.get_app_tag(app_name)
                    tag_bg = get_tag_color(tag)
                    if widgets['tag'].cget('text') != tag:
                        widgets['tag'].configure(text=tag, bg=tag_bg)
                        
            # Clean up removed apps
            to_remove = [name for name in self._row_widgets if name not in active_apps]
            for name in to_remove:
                self._row_widgets[name]['row'].destroy()
                del self._row_widgets[name]
                
            # Update total time
            counted = self.tracker.get_counted_seconds()
            self.total_label.configure(text=format_duration(counted))
            self._photo_refs = new_photo_refs
            
        except Exception:
            self._ui_refresh_scheduled = False

    def _toggle_include(self, app_name, var):
        self.tracker.set_included(app_name, bool(var.get()))
        self._refresh_app_list()

    def _show_report(self, report, is_new=True, is_live=False):
        if hasattr(self, '_report_window') and self._report_window and self._report_window.winfo_exists(): self._report_window.destroy()
        if hasattr(self, '_live_report_window') and self._live_report_window and self._live_report_window.winfo_exists(): self._live_report_window.destroy()
        win = tk.Toplevel(self.root)
        win.configure(bg=BG_SURFACE)
        win.option_add("*background", BG_SURFACE)
        win.option_add("*foreground", TEXT_PRIMARY)
        if is_live:
            self._live_report_window = win
            win.title("FocusLog — Live Report (Preview)")
        else:
            self._report_window = win
            win.title("FocusLog — Session Report")
        self._center_window(win, 720, 680)
        win.configure(bg=BG_SURFACE)
        win.minsize(600, 500)
        win.resizable(True, True)
        if os.path.exists(ICON_PATH):
            try: win.iconbitmap(ICON_PATH)
            except: pass
        win.lift()
        win.focus_force()

        hdr = tk.Frame(win, bg=BG_WHITE, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        title_text = "📊 Live Report (Preview)" if is_live else "📊 Session Report"
        tk.Label(hdr, text=title_text, bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 12, "bold")).pack(side="left", padx=14, pady=10)
        if is_live:
            tk.Button(hdr, text="🔄 Refresh", bg=BG_SURFACE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9), relief="flat", bd=0, padx=10, pady=5, cursor="hand2", command=lambda: (win.destroy(), self._show_live_report())).pack(side="right", padx=14, pady=6)
        elif is_new:
            def _save_and_close():
                try:
                    new_name = report_name_entry.get().strip()
                    report["session_name"] = new_name if new_name else "Unnamed"
                    save_to_history(report)
                    messagebox.showinfo("Saved", "Session saved to History.")
                    win.destroy()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to save: {e}")
            tk.Button(hdr, text="💾 Save to History", bg=ACCENT, fg="white", font=(FONT_FAMILY, 9, "bold"), relief="flat", bd=0, padx=12, pady=5, cursor="hand2", command=_save_and_close).pack(side="right", padx=14, pady=6)
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x")

        name_bar = tk.Frame(win, bg=BG_WHITE, height=40)
        name_bar.pack(fill="x", pady=(0, 1))
        name_bar.pack_propagate(False)
        tk.Label(name_bar, text="Session Name: ", bg=BG_WHITE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9)).pack(side="left", padx=(14, 8))
        report_name_entry = tk.Entry(name_bar, bg=BG_SURFACE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 10), bd=0, highlightthickness=1, highlightbackground=BORDER, width=40)
        report_name_entry.pack(side="left", pady=8)
        report_name_entry.insert(0, report.get("session_name", "").strip() or "Unnamed")
        if is_live:
            tk.Label(name_bar, text=f"🕒 Snapshot: {datetime.now().strftime('%H:%M:%S')} • Tracking continues...", bg=BG_WHITE, fg=ORANGE, font=(FONT_FAMILY, 8)).pack(side="right", padx=14, pady=10)

        # ── Export Footer (FIXED outside scrollable area — always visible) ──
        export_footer = tk.Frame(win, bg=BG_WHITE, height=50)
        export_footer.pack(side="bottom", fill="x")
        export_footer.pack_propagate(False)
        tk.Frame(win, bg=BORDER, height=1).pack(side="bottom", fill="x")

        def export_with_name(fmt):
            try:
                new_name = report_name_entry.get().strip()
                if new_name: report['session_name'] = new_name
            except Exception:
                pass
            self._export(report, fmt)
        tk.Button(export_footer, text="Export .txt", bg=ACCENT, fg="white", activebackground=ACCENT_HOVER, activeforeground="white", font=(FONT_FAMILY, 10, "bold"), bd=0, padx=16, pady=6, cursor="hand2", relief="flat", command=lambda: export_with_name("txt")).pack(side="left", padx=(20, 5), pady=8)
        tk.Button(export_footer, text="Export .json", bg=ACCENT, fg="white", activebackground=ACCENT_HOVER, activeforeground="white", font=(FONT_FAMILY, 10, "bold"), bd=0, padx=16, pady=6, cursor="hand2", relief="flat", command=lambda: export_with_name("json")).pack(side="left", padx=5, pady=8)
        tk.Button(export_footer, text="Export .csv", bg=ACCENT, fg="white", activebackground=ACCENT_HOVER, activeforeground="white", font=(FONT_FAMILY, 10, "bold"), bd=0, padx=16, pady=6, cursor="hand2", relief="flat", command=lambda: export_with_name("csv")).pack(side="left", padx=5, pady=8)

        # ── Scrollable Body ───────────────────────────────────────────────
        body_canvas = tk.Canvas(win, bg=BG_SURFACE, bd=0, highlightthickness=0)
        body_sb = ttk.Scrollbar(win, orient="vertical", command=body_canvas.yview)
        body = tk.Frame(body_canvas, bg=BG_SURFACE)
        body.bind("<Configure>", lambda e: body_canvas.configure(scrollregion=body_canvas.bbox("all")))
        body_win = body_canvas.create_window((0, 0), window=body, anchor="nw")
        body_canvas.configure(yscrollcommand=body_sb.set)
        body_canvas.pack(side="left", fill="both", expand=True)
        body_sb.pack(side="right", fill="y")
        body_canvas.bind("<Configure>", lambda e: body_canvas.itemconfig(body_win, width=e.width))

        # ── Safe Mousewheel Binding for Report Canvas ─────────────────────
        def _report_scroll(ev):
            body_canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")

        body_canvas.bind("<Enter>", lambda e: body_canvas.bind_all("<MouseWheel>", _report_scroll))
        body_canvas.bind("<Leave>", lambda e: body_canvas.unbind_all("<MouseWheel>"))
        px = 20
        card = tk.Frame(body, bg=BG_WHITE, bd=0, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", padx=px, pady=(12, 6))
        tk.Label(card, text=f"{report['date_display']}  ·  {report['start_display']} -> {report['end_display']}", bg=BG_WHITE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 10)).pack(anchor="w", padx=14, pady=(12, 4))
        tk.Label(card, text=f"Total session:  {report['total_formatted']}", bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 11)).pack(anchor="w", padx=14)
        tk.Label(card, text=f"Counted work:  {report['counted_formatted']}", bg=BG_WHITE, fg=ACCENT, font=(FONT_FAMILY, 11, "bold")).pack(anchor="w", padx=14, pady=(0, 6))
        if report.get("total_earned", 0) > 0:
            earned_frame = tk.Frame(card, bg=ACCENT_LIGHT)
            earned_frame.pack(fill="x", pady=(6, 12), padx=14)
            tk.Label(earned_frame, text="💰 Total Earned: ", bg=ACCENT_LIGHT, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 10)).pack(side="left", padx=10, pady=6)
            tk.Label(earned_frame, text=report["total_earned_display"], bg=ACCENT_LIGHT, fg=GREEN_STATUS, font=(FONT_FAMILY, 16, "bold")).pack(side="left", padx=6)
            tk.Label(earned_frame, text=f"@ {report['currency_symbol']}{report['hourly_rate']:.2f}/hr", bg=ACCENT_LIGHT, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9)).pack(side="left", padx=6)

        # ── Project Allocation Visuals ─────────────────────────────────────
        project_breakdown = report.get("project_breakdown", [])
        if project_breakdown:
            tk.Label(body, text="Project & Category Allocation", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 10, "bold")).pack(anchor="w", padx=px + 4, pady=(12, 4))
            
            alloc_card = tk.Frame(body, bg=BG_WHITE, highlightthickness=1, highlightbackground=BORDER)
            alloc_card.pack(fill="x", padx=px, pady=(0, 6))
            
            # Segmented horizontal bar canvas
            canvas = tk.Canvas(alloc_card, bg=BG_WHITE, height=20, bd=0, highlightthickness=0)
            canvas.pack(fill="x", padx=14, pady=(14, 10))
            
            def draw_segmented_bar(event=None):
                canvas.delete("all")
                w = canvas.winfo_width()
                h = canvas.winfo_height()
                if w < 10:
                    w = 640
                    
                total_secs = sum(pb["seconds"] for pb in project_breakdown)
                if total_secs <= 0:
                    canvas.create_rectangle(0, 0, w, h, fill="#E2E8F0", outline="")
                    return
                    
                current_x = 0
                for pb in project_breakdown:
                    pct = pb["seconds"] / total_secs
                    segment_w = pct * w
                    next_x = current_x + segment_w
                    canvas.create_rectangle(current_x, 0, next_x, h, fill=pb["color"], outline="")
                    current_x = next_x
            
            canvas.bind("<Configure>", draw_segmented_bar)
            
            legend_frame = tk.Frame(alloc_card, bg=BG_WHITE)
            legend_frame.pack(fill="x", padx=14, pady=(0, 14))
            
            for pb in project_breakdown:
                row_f = tk.Frame(legend_frame, bg=BG_WHITE)
                row_f.pack(fill="x", pady=2)
                
                swatch = tk.Label(row_f, text=" ■ ", bg=BG_WHITE, fg=pb["color"], font=(FONT_FAMILY, 10, "bold"))
                swatch.pack(side="left")
                
                lbl = tk.Label(row_f, text=pb["project"], bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9, "bold"))
                lbl.pack(side="left")
                
                pct_lbl = tk.Label(row_f, text=f"{pb['percent']:.1f}%", bg=BG_WHITE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9))
                pct_lbl.pack(side="left", padx=10)
                
                time_lbl = tk.Label(row_f, text=pb["formatted"], bg=BG_WHITE, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 9))
                time_lbl.pack(side="right")
                
                if pb.get("earned_display"):
                    earned_lbl = tk.Label(row_f, text=f"({pb['earned_display']})", bg=BG_WHITE, fg=GREEN_STATUS, font=(FONT_FAMILY, 9, "bold"))
                    earned_lbl.pack(side="right", padx=10)

        # ── App Breakdown (limited to 7 by default) ───────────────────────
        MAX_APPS_VISIBLE = 7
        all_apps = report["apps"]
        tk.Label(body, text="App Breakdown", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 10, "bold")).pack(anchor="w", padx=px + 4, pady=(12, 6))
        tbl = tk.Frame(body, bg=BG_WHITE, highlightthickness=1, highlightbackground=BORDER)
        tbl.pack(fill="x", padx=px)
        tbl.columnconfigure(0, weight=1)
        th = tk.Frame(tbl, bg=BG_SURFACE)
        th.pack(fill="x")
        th.columnconfigure(0, weight=1)
        for col, (txt, w, anc) in enumerate([("App", 0, "w"), ("Category", 12, "w"), ("Time", 12, "e"), ("% ", 6, "e"), ("Status", 10, "e")]):
            lbl = tk.Label(th, text=txt, bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9, "bold"), anchor=anc)
            if w: lbl.configure(width=w)
            lbl.grid(row=0, column=col, padx=10, pady=6, sticky="ew" if col == 0 or col == 1 else "e")
        th.columnconfigure(0, weight=1)
        th.columnconfigure(1, weight=0)

        app_rows_container = tk.Frame(tbl, bg=BG_WHITE)
        app_rows_container.pack(fill="x")

        def _render_app_rows(show_all=False):
            for w in app_rows_container.winfo_children():
                w.destroy()
            visible_apps = all_apps if show_all else all_apps[:MAX_APPS_VISIBLE]
            for i, app in enumerate(visible_apps):
                rbg = BG_WHITE if i % 2 == 0 else BG_SURFACE
                r = tk.Frame(app_rows_container, bg=rbg)
                r.pack(fill="x")
                r.columnconfigure(0, weight=1)
                r.columnconfigure(1, weight=0)
                excluded = app["excluded"]
                fg = TEXT_PRIMARY if not excluded else TEXT_DISABLED
                st_text = "✓ Counted" if not excluded else "✗ Excluded"
                st_fg = GREEN_STATUS if not excluded else RED_STATUS
                
                tag = app.get("tag", "Unassigned")
                tag_bg = get_tag_color(tag)
                
                tk.Label(r, text=app["name"], bg=rbg, fg=fg, font=(FONT_FAMILY, 10), anchor="w").grid(row=0, column=0, padx=10, pady=4, sticky="ew")
                
                tag_lbl = tk.Label(r, text=tag, bg=tag_bg, fg="#FFFFFF", font=(FONT_FAMILY, 7, "bold"), padx=5, pady=1, relief="flat")
                tag_lbl.grid(row=0, column=1, padx=10, pady=4, sticky="w")
                
                tk.Label(r, text=app["formatted"], bg=rbg, fg=fg, font=(FONT_FAMILY, 10), anchor="e", width=12).grid(row=0, column=2, padx=10, pady=4, sticky="e")
                tk.Label(r, text=f"{app['percent']:.0f}%", bg=rbg, fg=fg, font=(FONT_FAMILY, 10), anchor="e", width=6).grid(row=0, column=3, padx=10, pady=4, sticky="e")
                tk.Label(r, text=st_text, bg=rbg, fg=st_fg, font=(FONT_FAMILY, 9), anchor="e", width=10).grid(row=0, column=4, padx=10, pady=4, sticky="e")

        _render_app_rows(show_all=False)

        # "Show all / Show less" toggle if more than MAX_APPS_VISIBLE
        if len(all_apps) > MAX_APPS_VISIBLE:
            toggle_frame = tk.Frame(tbl, bg=BG_WHITE)
            toggle_frame.pack(fill="x")
            remaining = len(all_apps) - MAX_APPS_VISIBLE
            def _toggle_apps():
                is_expanded = toggle_btn.cget("text").startswith("▲")
                if is_expanded:
                    _render_app_rows(show_all=False)
                    toggle_btn.configure(text=f"▼ Show all ({remaining} more)")
                else:
                    _render_app_rows(show_all=True)
                    toggle_btn.configure(text="▲ Show less")
            toggle_btn = tk.Button(toggle_frame, text=f"▼ Show all ({remaining} more)", bg=BG_WHITE, fg=ACCENT, activebackground=BG_HOVER, activeforeground=ACCENT_HOVER, font=(FONT_FAMILY, 9, "underline"), bd=0, cursor="hand2", relief="flat", command=_toggle_apps)
            toggle_btn.pack(pady=6)

        # ── Timeline (limited to 20 by default) ──────────────────────────
        MAX_TIMELINE_VISIBLE = 20
        all_timeline = report["timeline"]
        tk.Label(body, text="Timeline", bg=BG_SURFACE, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 10, "bold")).pack(anchor="w", padx=px + 4, pady=(14, 6))
        tl_frame = tk.Frame(body, bg=BG_WHITE, highlightthickness=1, highlightbackground=BORDER)
        tl_frame.pack(fill="x", padx=px)
        if all_timeline:
            tl_rows_container = tk.Frame(tl_frame, bg=BG_WHITE)
            tl_rows_container.pack(fill="x")

            def _render_timeline_rows(show_all=False):
                for w in tl_rows_container.winfo_children():
                    w.destroy()
                visible = all_timeline if show_all else all_timeline[:MAX_TIMELINE_VISIBLE]
                for i, entry in enumerate(visible):
                    rbg = BG_WHITE if i % 2 == 0 else BG_SURFACE
                    tr = tk.Frame(tl_rows_container, bg=rbg)
                    tr.pack(fill="x")
                    tr.columnconfigure(1, weight=1)
                    t_start = entry['start'].strftime("%H:%M:%S") if hasattr(entry['start'], 'strftime') else entry['start']
                    t_end = entry['end'].strftime("%H:%M:%S") if hasattr(entry['end'], 'strftime') else entry['end']
                    tk.Label(tr, text=f"{t_start} -> {t_end}", bg=rbg, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9), anchor="w").grid(row=0, column=0, padx=10, pady=3, sticky="w")
                    tk.Label(tr, text=entry["app"], bg=rbg, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 10), anchor="w").grid(row=0, column=1, padx=10, pady=3, sticky="w")

            _render_timeline_rows(show_all=False)

            if len(all_timeline) > MAX_TIMELINE_VISIBLE:
                tl_toggle_frame = tk.Frame(tl_frame, bg=BG_WHITE)
                tl_toggle_frame.pack(fill="x")
                tl_remaining = len(all_timeline) - MAX_TIMELINE_VISIBLE
                def _toggle_timeline():
                    is_expanded = tl_toggle_btn.cget("text").startswith("▲")
                    if is_expanded:
                        _render_timeline_rows(show_all=False)
                        tl_toggle_btn.configure(text=f"▼ Show all ({tl_remaining} more)")
                    else:
                        _render_timeline_rows(show_all=True)
                        tl_toggle_btn.configure(text="▲ Show less")
                tl_toggle_btn = tk.Button(tl_toggle_frame, text=f"▼ Show all ({tl_remaining} more)", bg=BG_WHITE, fg=ACCENT, activebackground=BG_HOVER, activeforeground=ACCENT_HOVER, font=(FONT_FAMILY, 9, "underline"), bd=0, cursor="hand2", relief="flat", command=_toggle_timeline)
                tl_toggle_btn.pack(pady=6)
        else:
            tk.Label(tl_frame, text="No timeline entries recorded.", bg=BG_WHITE, fg=TEXT_DISABLED, font=(FONT_FAMILY, 10)).pack(padx=10, pady=10)

    def _export(self, report, fmt):
        if fmt == "txt": path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")], initialfile=f"focuslog_{report['date']}.txt")
        elif fmt == "json": path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")], initialfile=f"focuslog_{report['date']}.json")
        else: path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")], initialfile=f"focuslog_{report['date']}.csv")
        if not path: return
        try:
            if fmt == "txt": export_txt(report, path)
            elif fmt == "json": export_json(report, path)
            else: export_csv(report, path)
            messagebox.showinfo("Exported", f"Report saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _export_csv_history(self):
        sessions_dir = os.path.join(get_app_data_dir(), "sessions")
        if not os.path.exists(sessions_dir):
            messagebox.showwarning("No Sessions", "No saved sessions found.")
            return
        json_files = [f for f in os.listdir(sessions_dir) if f.endswith('.json')]
        if not json_files:
            messagebox.showwarning("No Sessions", "No saved sessions found.")
            return
        reports = []
        for filename in json_files:
            try: reports.append(load_session_json(os.path.join(sessions_dir, filename)))
            except Exception as e: print(f"Error loading {filename}: {e}")
        if not reports: messagebox.showerror("Error", "Could not load any sessions."); return
        default_name = f"FocusLog_Export_{datetime.now().strftime('%Y-%m-%d')}.csv"
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")], initialfile=default_name)
        if not filepath: return
        if export_csv_history(reports, filepath, hourly_rate=self.hourly_rate, currency_symbol=self.currency_symbol):
            messagebox.showinfo("Success", f"Exported {len(reports)} sessions to:\n{filepath}")
        else: messagebox.showerror("Error", "Failed to export CSV.")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = FocusLogApp()
    app.run()
