import os
import sys
import subprocess
from pathlib import Path

def get_app_data_dir() -> str:
    base_env = os.environ.get("LOCALAPPDATA")
    base = Path(base_env) if base_env else Path.home()
    path = base / "FocusLog"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)

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
            print(f"[FocusLog] Windows Recycle Bin failed: {e}")
            
    elif sys.platform == "darwin":
        try:
            abs_path = os.path.abspath(path)
            # Use AppleScript to delete (move to Trash) a POSIX file
            cmd = ['osascript', '-e', f'tell app "Finder" to delete (POSIX file "{abs_path}")']
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[FocusLog] macOS Trash failed: {e}")
            
    # Cross-platform fallback (permanent deletion)
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
    except Exception as e:
        print(f"[FocusLog] Permanent deletion fallback failed: {e}")
    return False

