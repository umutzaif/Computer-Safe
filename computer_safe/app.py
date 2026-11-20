"""Uygulamanın giriş noktası.

Kullanım:
    ComputerSafe.exe            -> yönetici şifresi sorulur, ayarlar penceresi açılır
    ComputerSafe.exe --start    -> kayıtlı ayarlarla koruma doğrudan başlar
                                   (Windows açılışında otomatik başlatma bunu kullanır)
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import sys
import threading
import tkinter as tk
from logging.handlers import RotatingFileHandler
from tkinter import messagebox

from computer_safe import APP_NAME, __version__, paths
from computer_safe.config import AppConfig
from computer_safe.gui.dialogs import PasswordGate, create_admin_password
from computer_safe.gui.monitor_window import MonitorWindow
from computer_safe.gui.settings_window import SettingsWindow
from computer_safe.mailer import Mailer
from computer_safe.monitor import ProtectionMonitor
from computer_safe.security import CredentialStore, CredentialStoreError

log = logging.getLogger(__name__)

ERROR_ALREADY_EXISTS = 183
_instance_mutex = None  # süreç boyunca açık kalmalı


class App:
    def __init__(self, start_protection: bool = False):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.report_callback_exception = self._report_tk_error
        self._start_immediately = start_protection

        self.config_path = paths.config_file()
        self.config = AppConfig.load(self.config_path)
        self.credentials = CredentialStore()
        self.gate = PasswordGate(lambda: self.config.admin_password_hash)
        self.settings: SettingsWindow | None = None

    def run(self) -> None:
        if not self.config.admin_password_hash:
            if not self._create_admin_password():
                return
            self.show_settings()
        elif self._start_immediately:
            self.root.after(0, self.start_protection, self.config)
        elif self._login():
            self.show_settings()
        else:
            return
        self.root.mainloop()

    # ---- ekranlar -----------------------------------------------------
    def _create_admin_password(self) -> bool:
        messagebox.showinfo(
            APP_NAME,
            "Computer-Safe'e hoş geldiniz!\n\nÖnce bir yönetici şifresi belirleyin. Bu şifre olmadan "
            "koruma durdurulamaz ve ayarlar açılamaz.",
            parent=self.root,
        )
        password_hash = create_admin_password(self.root)
        if not password_hash:
            return False
        self.config.admin_password_hash = password_hash
        self.config.save(self.config_path)
        return True

    def _login(self) -> bool:
        while True:
            result = self.gate.ask(self.root, APP_NAME, "Ayarları açmak için yönetici şifresini girin:")
            if result is None:
                return False
            if result:
                return True

    def show_settings(self) -> None:
        if self.settings is None:
            self.settings = SettingsWindow(
                self.root, self.config, self.config_path, self.credentials, self.gate, self.start_protection
            )
        self.root.deiconify()
        self.root.lift()

    def start_protection(self, config: AppConfig) -> None:
        self.config = config
        mailer = Mailer(config.email, lambda: self._smtp_password(config.email.sender), paths.outbox_dir())
        mailer.start()
        monitor = ProtectionMonitor(config, mailer)
        monitor.start()
        log.info("Koruma başlatıldı")
        self.root.withdraw()
        MonitorWindow(self.root, monitor, mailer, self.gate, on_stopped=self._on_protection_stopped)

    def _on_protection_stopped(self) -> None:
        log.info("Koruma kullanıcı tarafından durduruldu")
        self.show_settings()

    # ---- yardımcılar --------------------------------------------------
    def _smtp_password(self, sender: str) -> str | None:
        try:
            return self.credentials.get_smtp_password(sender)
        except CredentialStoreError:
            log.exception("SMTP şifresi okunamadı")
            return None

    def _report_tk_error(self, exc_type, exc_value, exc_tb) -> None:
        log.error("Arayüz hatası", exc_info=(exc_type, exc_value, exc_tb))
        messagebox.showerror(APP_NAME, f"Beklenmeyen bir hata oluştu:\n{exc_value}\n\nAyrıntılar log dosyasında.")


# ---------------------------------------------------------------------------
def setup_logging() -> None:
    handler = RotatingFileHandler(
        paths.logs_dir() / "computer_safe.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handlers: list[logging.Handler] = [handler]
    if sys.stderr is not None:  # pencereli exe'de konsol yoktur
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
    )

    def log_uncaught(exc_type, exc_value, exc_tb) -> None:
        logging.getLogger(APP_NAME).critical("Yakalanmamış hata", exc_info=(exc_type, exc_value, exc_tb))

    def log_thread_exception(args: threading.ExceptHookArgs) -> None:
        log_uncaught(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = log_uncaught
    threading.excepthook = log_thread_exception


def acquire_single_instance() -> bool:
    """Aynı anda iki kopya çalışıp kamerayı paylaşmaya çalışmasın."""
    global _instance_mutex
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _instance_mutex = kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}SingleInstance")
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def self_test() -> bool:
    """Kurulumu kontrol eder (log dosyasına yazar): ses dosyaları, şifre kasası, kamera."""
    from computer_safe.monitor import CRITICAL_SOUND, WARNING_SOUND, open_camera

    results: dict[str, bool] = {}
    results["ses dosyaları"] = all(paths.resource_path(s).exists() for s in (WARNING_SOUND, CRITICAL_SOUND))
    store = CredentialStore(service=f"{APP_NAME}-selftest")
    try:
        store.set_smtp_password("selftest@example.com", "ok")
        results["şifre kasası"] = store.get_smtp_password("selftest@example.com") == "ok"
        store.delete_smtp_password("selftest@example.com")
    except CredentialStoreError:
        log.exception("Şifre kasası testi")
        results["şifre kasası"] = False
    config = AppConfig.load(paths.config_file())
    capture = open_camera(config.detection.camera_index)
    results["kamera"] = bool(capture.isOpened())
    capture.release()
    for name, ok in results.items():
        log.info("Öz test - %s: %s", name, "TAMAM" if ok else "HATA")
    return all(results.values())


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Kamera ile bilgisayar koruma")
    parser.add_argument("--start", action="store_true", help="Kayıtlı ayarlarla korumayı hemen başlat")
    parser.add_argument("--self-test", action="store_true", help="Kurulumu kontrol et, sonucu log'a yaz")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    setup_logging()
    log.info("%s %s başlatılıyor", APP_NAME, __version__)
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    if not acquire_single_instance():
        messagebox.showinfo(APP_NAME, "Computer-Safe zaten çalışıyor.")
        return
    try:
        App(start_protection=args.start).run()
    except Exception as exc:
        log.exception("Uygulama beklenmeyen bir hatayla kapandı")
        messagebox.showerror(APP_NAME, f"Beklenmeyen bir hata oluştu:\n{exc}")
