import os
import sys
from pathlib import Path
import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(autouse=True)
def isolate_test_environment(tmp_path, monkeypatch):
    """
    Globally isolates LOCALAPPDATA and APPDATA for all pytest executions,
    preventing any test from reading or overwriting user profile data.
    """
    test_appdata = str(tmp_path / "AppDataLocal")
    os.makedirs(test_appdata, exist_ok=True)
    monkeypatch.setenv("LOCALAPPDATA", test_appdata)
    monkeypatch.setenv("APPDATA", test_appdata)
    yield
