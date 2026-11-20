"""Şifre güvenliği.

İki farklı şifre türü vardır ve ikisi farklı yöntemlerle korunur:

1. Yönetici şifresi (korumayı durdurmak / ayarları açmak için):
   Sadece doğrulanması gerekir, geri okunması gerekmez. Bu yüzden tek yönlü
   PBKDF2-HMAC-SHA256 (600.000 iterasyon, rastgele 16 baytlık tuz) ile özetlenir
   ve yalnızca özet saklanır.

2. E-posta (SMTP) şifresi:
   SMTP sunucusuna giriş yaparken şifrenin kendisi gönderilmek zorundadır; özet
   (hash) tek yönlü olduğu için burada kullanılamaz. Bu şifre Windows Kimlik
   Bilgisi Yöneticisi'nde (Credential Manager, DPAPI ile kullanıcı hesabınıza
   bağlı olarak şifrelenir) saklanır. Diske düz metin olarak asla yazılmaz.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import sys

import keyring
from keyring.backend import KeyringBackend
from keyring.errors import KeyringError, PasswordDeleteError

from computer_safe import APP_NAME

log = logging.getLogger(__name__)

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000  # OWASP önerisi (PBKDF2-HMAC-SHA256)
SALT_BYTES = 16
MIN_ADMIN_PASSWORD_LENGTH = 6


# ---------------------------------------------------------------------------
# Yönetici şifresi: tek yönlü özet
# ---------------------------------------------------------------------------
def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Şifreyi tuzlu PBKDF2 ile özetler: 'pbkdf2_sha256$iter$tuz$özet'."""
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [PBKDF2_ALGORITHM, str(iterations), _b64encode(salt), _b64encode(digest)]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Şifreyi saklanan özetle sabit zamanlı karşılaştırarak doğrular."""
    try:
        algorithm, iterations_text, salt_text, digest_text = stored_hash.split("$")
        if algorithm != PBKDF2_ALGORITHM:
            return False
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
        iterations = int(iterations_text)
    except (ValueError, TypeError):
        log.warning("Saklanan şifre özeti okunamadı")
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


# ---------------------------------------------------------------------------
# E-posta şifresi: Windows Kimlik Bilgisi Yöneticisi
# ---------------------------------------------------------------------------
class CredentialStoreError(Exception):
    """Güvenli şifre deposuna erişilemedi."""


def _default_backend() -> KeyringBackend:
    if sys.platform == "win32":
        # PyInstaller ile paketlendiğinde otomatik arka uç keşfi güvenilir olmadığı
        # için Windows kasası doğrudan seçilir.
        from keyring.backends.Windows import WinVaultKeyring

        return WinVaultKeyring()
    return keyring.get_keyring()


class CredentialStore:
    """SMTP şifrelerini işletim sisteminin güvenli kasasında saklar."""

    def __init__(self, backend: KeyringBackend | None = None, service: str = APP_NAME):
        self._backend = backend
        self._service = service

    @property
    def backend(self) -> KeyringBackend:
        if self._backend is None:
            self._backend = _default_backend()
        return self._backend

    @staticmethod
    def _username(account: str) -> str:
        return f"smtp:{account.strip().lower()}"

    def set_smtp_password(self, account: str, password: str) -> None:
        try:
            self.backend.set_password(self._service, self._username(account), password)
        except KeyringError as exc:
            raise CredentialStoreError(f"Şifre güvenli kasaya kaydedilemedi: {exc}") from exc

    def get_smtp_password(self, account: str) -> str | None:
        if not account:
            return None
        try:
            return self.backend.get_password(self._service, self._username(account))
        except KeyringError as exc:
            raise CredentialStoreError(f"Şifre güvenli kasadan okunamadı: {exc}") from exc

    def delete_smtp_password(self, account: str) -> None:
        if not account:
            return
        try:
            self.backend.delete_password(self._service, self._username(account))
        except PasswordDeleteError:
            pass  # zaten yok
        except KeyringError as exc:
            raise CredentialStoreError(f"Şifre güvenli kasadan silinemedi: {exc}") from exc
