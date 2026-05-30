"""
TrueHour — App info resolver.
Extracts friendly display names and icons from Windows executables.
"""
import platform
SYSTEM = platform.system()

if SYSTEM == "Windows":
    import win32gui
    import win32ui
    import win32api
    import win32con
    import win32process
import psutil
from PIL import Image
import os
import logging
from functools import lru_cache
from config import get_app_data_dir

# Configure logging for security events
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)

_name_cache = {}
OVERRIDES_FILE = os.path.join(get_app_data_dir(), "name_overrides.txt")
_NAME_OVERRIDES = {}

def _load_name_overrides():
    global _NAME_OVERRIDES
    if not os.path.exists(OVERRIDES_FILE):
        try:
            override_dir = os.path.dirname(OVERRIDES_FILE)
            if override_dir:
                os.makedirs(override_dir, exist_ok=True)
            with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
                f.write("# Add your custom app name overrides here. Format: exename=Friendly Name\n")
                f.write("# Example: chrome=Google Chrome\n")
        except OSError as e:
            logger.warning(f"Failed to create name overrides file: {e}")
    else:
        try:
            with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        _NAME_OVERRIDES[k.strip().lower()] = v.strip()
        except (OSError, IOError) as e:
            logger.warning(f"Failed to read name overrides file: {e}")

_load_name_overrides()

def get_foreground_app_info():
    """Return (friendly_name, exe_path) for the current foreground window."""
    if SYSTEM != "Windows":
        # macOS Implementation using native AppKit
        try:
            from AppKit import NSWorkspace
            active_app = NSWorkspace.sharedWorkspace().activeApplication()
            if not active_app:
                return "[Idle]", ""
            friendly = active_app.get("NSApplicationName", "[Idle]")
            exe_path = active_app.get("NSApplicationPath", "")
            
            # Match against name overrides
            key = friendly.lower()
            if key in _NAME_OVERRIDES:
                friendly = _NAME_OVERRIDES[key]
                
            return friendly, exe_path
        except Exception as e:
            logger.warning(f"Error getting foreground app info on macOS: {e}")
            return "[Idle]", ""

    # Windows Implementation
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return "[Idle]", ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid <= 0:
            return "[Idle]", ""
        try:
            proc = psutil.Process(pid)
            exe_path = proc.exe()
            base = proc.name()
            if base.lower().endswith(".exe"):
                base = base[:-4]
            friendly = resolve_name(exe_path, base)
            return friendly, exe_path
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            title = win32gui.GetWindowText(hwnd)
            return title if title else "[Protected System App]", ""
    except Exception as e:
        logger.warning(f"Error getting foreground app info: {e}")
        return "[Idle]", ""

def resolve_name(exe_path, base_name):
    if exe_path in _name_cache: return _name_cache[exe_path]
    friendly = None
    key = base_name.lower()
    if key in _NAME_OVERRIDES: friendly = _NAME_OVERRIDES[key]
    if not friendly: friendly = _get_file_description(exe_path)
    if not friendly: friendly = base_name.replace("_", " ").replace("-", " ").title()
    _name_cache[exe_path] = friendly
    return friendly

def _get_file_description(exe_path):
    """Extract FileDescription from an executable's version info."""
    if SYSTEM != "Windows":
        return None
    try:
        lang, codepage = win32api.GetFileVersionInfo(exe_path, '\\VarFileInfo\\Translation')[0]
        path = f'\\StringFileInfo\\{lang:04X}{codepage:04X}\\FileDescription'
        desc = win32api.GetFileVersionInfo(exe_path, path)
        if desc and desc.strip():
            return desc.strip()
    except Exception as e:
        logger.debug(f"Failed to get file description for {exe_path}: {e}")
    return None

@lru_cache(maxsize=128)
def get_icon_image(exe_path: str, size: int = 16):
    if not exe_path: return None
    return _extract_icon(exe_path, size)

def _extract_icon(exe_path, size=16):
    if SYSTEM != "Windows":
        # macOS Icon Extraction using native Cocoa / AppKit
        try:
            from AppKit import NSWorkspace
            import io
            
            workspace = NSWorkspace.sharedWorkspace()
            ns_image = workspace.iconForFile_(exe_path)
            if ns_image:
                # Convert NSImage to PNG data, then load into Pillow
                tiff_data = ns_image.TIFFRepresentation()
                img = Image.open(io.BytesIO(tiff_data))
                resampler = getattr(Image, 'Resampling', Image).LANCZOS
                return img.resize((size, size), resampler)
        except Exception as e:
            logger.debug(f"Failed to extract icon from {exe_path} on macOS: {e}")
            return None
        return None

    # Windows Icon Extraction
    large_icons, small_icons = [], []
    screen_dc = None
    mem_dc = None
    bmp = None
    old_bmp = None
    try:
        large_icons, small_icons = win32gui.ExtractIconEx(exe_path, 0, 1)
        if not small_icons and not large_icons:
            return None
        hicon = small_icons[0] if small_icons else large_icons[0]
        screen_dc = win32gui.GetDC(0)
        hdc = win32ui.CreateDCFromHandle(screen_dc)
        mem_dc = hdc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(hdc, size, size)
        old_bmp = mem_dc.SelectObject(bmp)
        
        brush = win32gui.GetSysColorBrush(win32con.COLOR_WINDOW)
        win32gui.FillRect(mem_dc.GetHandleOutput(), (0, 0, size, size), brush)
        win32gui.DrawIconEx(mem_dc.GetHandleOutput(), 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)
        
        bmp_info = bmp.GetInfo()
        bmp_bits = bmp.GetBitmapBits()
        img = Image.frombuffer('RGBA', (bmp_info['bmWidth'], bmp_info['bmHeight']), bmp_bits, 'raw', 'BGRA', 0, 1)
        
        # Handle Pillow deprecation
        resampler = getattr(Image, 'Resampling', Image).LANCZOS
        return img.resize((size, size), resampler)
    except Exception as e:
        logger.debug(f"Failed to extract icon from {exe_path}: {e}")
        return None
    finally:
        if mem_dc:
            if old_bmp:
                try: mem_dc.SelectObject(old_bmp)
                except Exception: pass
            try: mem_dc.DeleteDC()
            except Exception: pass
        if bmp:
            try: win32gui.DeleteObject(bmp.GetHandle())
            except Exception: pass
        if screen_dc:
            try: win32gui.ReleaseDC(0, screen_dc)
            except Exception: pass
        for icon in large_icons:
            try: win32gui.DestroyIcon(icon)
            except Exception: pass
        for icon in small_icons:
            try: win32gui.DestroyIcon(icon)
            except Exception: pass

def get_running_applications():
    apps = set()
    results = []
    
    if SYSTEM != "Windows":
        # macOS Implementation using Cocoa / AppKit
        try:
            from AppKit import NSWorkspace, NSApplicationActivationPolicyRegular
            running_apps = NSWorkspace.sharedWorkspace().runningApplications()
            for app in running_apps:
                if app.activationPolicy() == NSApplicationActivationPolicyRegular:
                    name = app.localizedName()
                    bundle_path = app.bundleURL().path() if app.bundleURL() else ""
                    
                    # Match against overrides
                    key = name.lower()
                    if key in _NAME_OVERRIDES:
                        name = _NAME_OVERRIDES[key]
                        
                    if name and name not in apps:
                        apps.add(name)
                        results.append((name, bundle_path))
        except Exception as e:
            logger.debug(f"Failed to get running apps on macOS: {e}")
        return sorted(results, key=lambda x: x[0].lower())

    # Windows Implementation
    def enum_windows_proc(hwnd, lParam):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if not (ex_style & win32con.WS_EX_TOOLWINDOW):
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid > 0:
                        proc = psutil.Process(pid)
                        exe_path = proc.exe()
                        base = proc.name()
                        if base.lower().endswith(".exe"):
                            base = base[:-4]
                        friendly = resolve_name(exe_path, base)
                        if friendly and friendly != "[Idle]" and friendly not in apps:
                            apps.add(friendly)
                            results.append((friendly, exe_path))
                except Exception as e:
                    logger.debug(f"Error enumerating window {hwnd}: {e}")
        return True
    win32gui.EnumWindows(enum_windows_proc, 0)
    return sorted(results, key=lambda x: x[0].lower())
