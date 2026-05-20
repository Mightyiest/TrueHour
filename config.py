import os
from pathlib import Path

def get_app_data_dir() -> str:
    base_env = os.environ.get("LOCALAPPDATA")
    base = Path(base_env) if base_env else Path.home()
    path = base / "FocusLog"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
