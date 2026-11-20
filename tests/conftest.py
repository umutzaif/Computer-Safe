import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def isolated_app_home(tmp_path, monkeypatch):
    """Testler gerçek %APPDATA% klasörüne dokunmasın."""
    monkeypatch.setenv("COMPUTER_SAFE_HOME", str(tmp_path / "home"))
