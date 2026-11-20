from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from computer_safe.security import CredentialStore, hash_password, verify_password


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.data = {}

    def set_password(self, service, username, password):
        self.data[(service, username)] = password

    def get_password(self, service, username):
        return self.data.get((service, username))

    def delete_password(self, service, username):
        if (service, username) not in self.data:
            raise PasswordDeleteError("yok")
        del self.data[(service, username)]


def test_hash_does_not_contain_password_and_verifies():
    stored = hash_password("gizli-sifre", iterations=1000)
    assert "gizli-sifre" not in stored
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert verify_password("gizli-sifre", stored)
    assert not verify_password("yanlis-sifre", stored)


def test_same_password_gets_different_salt():
    assert hash_password("abc123", iterations=1000) != hash_password("abc123", iterations=1000)


def test_malformed_hash_is_rejected():
    assert not verify_password("x", "")
    assert not verify_password("x", "md5$1$abc$def")
    assert not verify_password("x", "pbkdf2_sha256$notanumber$AAAA$AAAA")


def test_credential_store_roundtrip():
    backend = MemoryKeyring()
    store = CredentialStore(backend=backend)
    store.set_smtp_password("Kisi@Example.com", "app-password")
    assert store.get_smtp_password("kisi@example.com") == "app-password"
    store.delete_smtp_password("kisi@example.com")
    assert store.get_smtp_password("kisi@example.com") is None
    store.delete_smtp_password("kisi@example.com")  # yoksa hata vermemeli
    assert store.get_smtp_password("") is None
