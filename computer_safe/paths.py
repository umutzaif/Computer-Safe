"""Uygulamanın kullandığı dosya ve klasör yolları."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from computer_safe import APP_NAME


def app_data_dir() -> Path:
    """Ayarların, logların ve e-posta kuyruğunun tutulduğu klasör (%APPDATA%\\ComputerSafe).

    Testlerde COMPUTER_SAFE_HOME ortam değişkeniyle başka bir klasör verilebilir.
    """
    override = os.environ.get("COMPUTER_SAFE_HOME")
    if override:
        path = Path(override)
    else:
        base = os.environ.get("APPDATA") or str(Path.home())
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file() -> Path:
    return app_data_dir() / "config.json"


def outbox_dir() -> Path:
    return app_data_dir() / "outbox"


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_recordings_dir() -> Path:
    return Path.home() / "Videos" / APP_NAME


def resource_path(relative: str) -> Path:
    """Paketlenmiş (PyInstaller) ya da kaynak koddan çalışırken varlık dosyalarının yolu."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / relative
