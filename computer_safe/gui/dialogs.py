"""Şifre diyalogları."""

from __future__ import annotations

import logging
import time
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Callable

from computer_safe.security import MIN_ADMIN_PASSWORD_LENGTH, hash_password, verify_password

log = logging.getLogger(__name__)


def ask_password(parent: tk.Misc, title: str, prompt: str) -> str | None:
    return simpledialog.askstring(title, prompt, show="*", parent=parent)


def create_admin_password(parent: tk.Misc) -> str | None:
    """Yeni yönetici şifresi ister ve PBKDF2 özetini döndürür (iptalde None)."""
    while True:
        password = ask_password(
            parent,
            "Yönetici şifresi oluştur",
            "Korumayı durdurmak ve ayarları açmak için kullanılacak\n"
            f"yönetici şifresini belirleyin (en az {MIN_ADMIN_PASSWORD_LENGTH} karakter):",
        )
        if password is None:
            return None
        if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
            messagebox.showwarning(
                "Computer-Safe", f"Şifre en az {MIN_ADMIN_PASSWORD_LENGTH} karakter olmalı.", parent=parent
            )
            continue
        confirm = ask_password(parent, "Yönetici şifresi oluştur", "Şifreyi tekrar girin:")
        if confirm is None:
            return None
        if confirm != password:
            messagebox.showwarning("Computer-Safe", "Şifreler eşleşmiyor, tekrar deneyin.", parent=parent)
            continue
        return hash_password(password)


class PasswordGate:
    """Yönetici şifresini doğrular; art arda hatalı girişlerde kısa süre kilitler."""

    MAX_ATTEMPTS = 3
    LOCKOUT_SECONDS = 30

    def __init__(self, stored_hash: Callable[[], str]):
        self._stored_hash = stored_hash
        self._failures = 0
        self._locked_until = 0.0

    def ask(self, parent: tk.Misc, title: str, prompt: str) -> bool | None:
        """True: doğru şifre, False: yanlış/kilitli, None: kullanıcı vazgeçti."""
        remaining = self._locked_until - time.monotonic()
        if remaining > 0:
            messagebox.showwarning(
                title, f"Çok fazla hatalı deneme. {int(remaining) + 1} sn sonra tekrar deneyin.", parent=parent
            )
            return False

        password = ask_password(parent, title, prompt)
        if password is None:
            return None
        if verify_password(password, self._stored_hash()):
            self._failures = 0
            return True

        self._failures += 1
        log.warning("Hatalı yönetici şifresi denemesi (%d)", self._failures)
        if self._failures >= self.MAX_ATTEMPTS:
            self._failures = 0
            self._locked_until = time.monotonic() + self.LOCKOUT_SECONDS
            messagebox.showerror(
                title, f"Çok fazla hatalı deneme. {self.LOCKOUT_SECONDS} sn bekleyin.", parent=parent
            )
        else:
            messagebox.showerror(title, "Şifre hatalı.", parent=parent)
        return False
