import os
import sys
import subprocess
import shutil
import json
from pathlib import Path

class DynamicPath(os.PathLike):
    def __init__(self, resolver):
        self._resolver = resolver

    def __fspath__(self) -> str:
        return str(self._resolver())

    def __str__(self) -> str:
        return str(self._resolver())

    def __repr__(self) -> str:
        return repr(self._resolver())

    def __eq__(self, other) -> bool:
        if isinstance(other, DynamicPath):
            return str(self) == str(other)
        return str(self) == other

    def __hash__(self) -> int:
        return hash(str(self))

    def __len__(self) -> int:
        return len(str(self))

    def __getitem__(self, index):
        return str(self)[index]

    def __add__(self, other) -> str:
        return str(self) + other

    def __radd__(self, other) -> str:
        return other + str(self)


def get_app_data_root() -> str:
    base_env = os.environ.get("LOCALAPPDATA")
    base = Path(base_env) if base_env else Path.home()
    new_path = base / "TrueHour"
    new_path.mkdir(parents=True, exist_ok=True)
    return str(new_path)

def get_app_data_dir() -> str:
    root_dir = Path(get_app_data_root())
    
    # Ensure legacy migration from old FocusLog app to TrueHour root
    old_path = root_dir.parent / "FocusLog"
    if old_path.exists() and not (root_dir / "profiles.json").exists():
        for file in old_path.glob("*"):
            dest = root_dir / file.name
            if not dest.exists():
                try:
                    if file.is_dir():
                        shutil.copytree(file, dest)
                    else:
                        shutil.copy2(file, dest)
                except Exception:
                    pass

    profiles_file = root_dir / "profiles.json"
    
    # Load/Initialize profiles.json
    profiles_data = {"active_profile": "Default", "profiles": ["Default"]}
    if profiles_file.exists():
        try:
            with open(profiles_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict) and "active_profile" in loaded and "profiles" in loaded:
                    profiles_data = loaded
        except Exception:
            pass
    else:
        # Create profiles.json on first run
        try:
            with open(profiles_file, "w", encoding="utf-8") as f:
                json.dump(profiles_data, f, indent=4)
        except Exception:
            pass
            
    active_profile = profiles_data.get("active_profile", "Default")
    profile_dir = root_dir / "profiles" / active_profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    # ── Legacy Migration to 'Default' Profile ──
    # If legacy files exist in TrueHour root, move them into TrueHour/profiles/Default on first launch
    if active_profile == "Default":
        legacy_files = [
            "app_settings.json", "settings.json", "tags.json",
            "auto_excluded_apps.txt", "truehour.db"
        ]
        legacy_dirs = ["sessions", "autosave", "qr_codes"]
        
        # Check if legacy files exist in root
        has_legacy = any((root_dir / f).exists() for f in legacy_files + legacy_dirs)
        if has_legacy:
            for filename in legacy_files:
                src = root_dir / filename
                dst = profile_dir / filename
                if src.exists() and not dst.exists():
                    try:
                        shutil.move(str(src), str(dst))
                    except Exception:
                        pass
            for dirname in legacy_dirs:
                src = root_dir / dirname
                dst = profile_dir / dirname
                if src.exists() and not dst.exists():
                    try:
                        shutil.move(str(src), str(dst))
                    except Exception:
                        pass
                        
    return str(profile_dir)

def open_file(path: str) -> None:
    """Open a file or folder using the default system handler in a cross-platform manner."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])

def send_to_trash(path: str) -> bool:
    """Move a file to the system's recycle bin/trash in a cross-platform manner."""
    if not os.path.exists(path):
        return False
        
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            
            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR),
                    ("fFlags", wintypes.USHORT),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", wintypes.LPVOID),
                    ("lpszProgressTitle", wintypes.LPCWSTR),
                ]
            
            FO_DELETE = 3
            FOF_ALLOWUNDO = 0x0040
            FOF_NOCONFIRMATION = 0x0010
            FOF_NOERRORUI = 0x0400
            
            abs_path = os.path.abspath(path)
            path_dn = abs_path + "\0\0"
            
            fileop = SHFILEOPSTRUCTW()
            fileop.hwnd = None
            fileop.wFunc = FO_DELETE
            fileop.pFrom = path_dn
            fileop.pTo = None
            fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI
            
            shell32 = ctypes.windll.shell32
            result = shell32.SHFileOperationW(ctypes.byref(fileop))
            if result == 0:
                return True
        except Exception as e:
            print(f"[TrueHour] Windows Recycle Bin failed: {e}")
            
    elif sys.platform == "darwin":
        try:
            abs_path = os.path.abspath(path)
            # Use AppleScript to delete (move to Trash) a POSIX file
            cmd = ['osascript', '-e', f'tell app "Finder" to delete (POSIX file "{abs_path}")']
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[TrueHour] macOS Trash failed: {e}")
            
    # Cross-platform fallback (permanent deletion)
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
    except Exception as e:
        print(f"[TrueHour] Permanent deletion fallback failed: {e}")
    return False


