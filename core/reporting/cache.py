import os
import hashlib
import shutil
from config import get_app_data_dir


def get_cache_dir() -> str:
    cache_path = os.path.join(get_app_data_dir(), "report_cache")
    os.makedirs(cache_path, exist_ok=True)
    return cache_path


def compute_cache_key(
    report_type: str, start_date: str, end_date: str, export_format: str
) -> str:
    key_str = f"{report_type}_{start_date}_{end_date}_{export_format}"
    return hashlib.sha256(key_str.encode("utf-8")).hexdigest()


def get_cached_report(
    report_type: str, start_date: str, end_date: str, export_format: str
) -> str | None:
    key = compute_cache_key(report_type, start_date, end_date, export_format)
    cache_file = os.path.join(get_cache_dir(), f"{key}.{export_format}")
    if os.path.exists(cache_file):
        import time

        # Expire cache entries older than 24 hours
        if time.time() - os.path.getmtime(cache_file) < 86400:
            return cache_file
        else:
            try:
                os.remove(cache_file)
            except Exception:
                pass
    return None


def save_to_cache(
    report_type: str, start_date: str, end_date: str, export_format: str, filepath: str
):
    key = compute_cache_key(report_type, start_date, end_date, export_format)
    cache_file = os.path.join(get_cache_dir(), f"{key}.{export_format}")
    try:
        shutil.copy2(filepath, cache_file)
    except Exception as e:
        print(f"[Cache] Saving to cache failed: {e}")
