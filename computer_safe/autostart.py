"""Windows açılışında korumanın otomatik başlaması (HKCU\\...\\Run kaydı)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from computer_safe import APP_NAME

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller ile paketlenmiş exe
        return f'"{sys.executable}" --start'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(__file__).resolve().parent.parent / "koruma.py"
    return f'"{pythonw}" "{script}" --start'


def set_autostart(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
            log.info("Otomatik başlatma etkinleştirildi")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
                log.info("Otomatik başlatma kapatıldı")
            except FileNotFoundError:
                pass


def is_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
