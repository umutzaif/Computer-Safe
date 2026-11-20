"""Alarm sesleri ve saldırı eşiğinde uygulanan sistem işlemleri (kilitle / kapat)."""

from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
import threading
from pathlib import Path

from computer_safe.config import FinalAction

try:  # winsound yalnızca Windows'ta vardır
    import winsound
except ImportError:  # pragma: no cover
    winsound = None

log = logging.getLogger(__name__)

SHUTDOWN_DELAY_SECONDS = 60
CREATE_NO_WINDOW = 0x08000000


class SoundPlayer:
    """Ana döngüyü bloklamadan bip ve WAV sesleri çalar."""

    def __init__(self) -> None:
        self._beep_lock = threading.Lock()

    def beep(self, frequency: int = 1000, duration_ms: int = 300) -> None:
        """Arka planda bip sesi çalar; önceki bip bitmediyse yenisini atlar."""
        if winsound is None or not self._beep_lock.acquire(blocking=False):
            return

        def worker() -> None:
            try:
                winsound.Beep(frequency, duration_ms)
            except RuntimeError:
                log.debug("Bip sesi çalınamadı", exc_info=True)
            finally:
                self._beep_lock.release()

        threading.Thread(target=worker, name="beep", daemon=True).start()

    def play_wav(self, path: Path) -> None:
        if winsound is None:
            return
        if not path.exists():
            log.warning("Ses dosyası bulunamadı: %s", path)
            return
        try:
            winsound.PlaySound(
                str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            )
        except RuntimeError:
            log.exception("Ses dosyası çalınamadı: %s", path)

    def stop(self) -> None:
        if winsound is not None:
            try:
                winsound.PlaySound(None, 0)
            except RuntimeError:
                pass


def lock_workstation() -> None:
    if sys.platform != "win32":
        log.warning("Ekran kilitleme yalnızca Windows'ta destekleniyor")
        return
    if not ctypes.windll.user32.LockWorkStation():
        log.error("Ekran kilitlenemedi")


def schedule_shutdown(delay_seconds: int = SHUTDOWN_DELAY_SECONDS) -> None:
    """Windows'u gecikmeli kapatır. İptal etmek için: shutdown /a"""
    if sys.platform != "win32":
        log.warning("Kapatma yalnızca Windows'ta destekleniyor")
        return
    message = "Computer-Safe: Saldiri esigi asildi, bilgisayar kapatiliyor."
    try:
        subprocess.run(
            ["shutdown", "/s", "/t", str(delay_seconds), "/c", message],
            check=True,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.CalledProcessError):
        log.exception("Kapatma komutu çalıştırılamadı")


def perform_final_action(action: FinalAction) -> None:
    log.warning("Son işlem uygulanıyor: %s", action.value)
    if action is FinalAction.LOCK:
        lock_workstation()
    elif action is FinalAction.SHUTDOWN:
        schedule_shutdown()
