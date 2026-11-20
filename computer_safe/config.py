"""Kullanıcı ayarları: JSON olarak %APPDATA%\\ComputerSafe\\config.json içinde saklanır.

Not: E-posta şifresi bu dosyada TUTULMAZ. Şifre Windows Kimlik Bilgisi Yöneticisi'nde
(bkz. security.CredentialStore), yönetici şifresi ise yalnızca PBKDF2 özeti olarak saklanır.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any

from computer_safe.paths import default_recordings_dir

log = logging.getLogger(__name__)

CONFIG_VERSION = 1

# Hazır SMTP sunucuları: görünen ad -> (sunucu, port)
SMTP_PRESETS: dict[str, tuple[str, int]] = {
    "Outlook / Hotmail": ("smtp-mail.outlook.com", 587),
    "Microsoft 365 (iş/okul)": ("smtp.office365.com", 587),
    "Gmail": ("smtp.gmail.com", 587),
    "Yandex": ("smtp.yandex.com", 465),
    "Özel": ("", 587),
}


class FinalAction(str, Enum):
    """Saldırı eşiği aşıldığında yapılacak işlem."""

    NONE = "none"
    LOCK = "lock"
    SHUTDOWN = "shutdown"

    @property
    def label(self) -> str:
        return {
            FinalAction.NONE: "Hiçbir şey yapma",
            FinalAction.LOCK: "Ekranı kilitle",
            FinalAction.SHUTDOWN: "Bilgisayarı kapat (60 sn sonra)",
        }[self]


@dataclass
class DetectionSettings:
    camera_index: int = 0
    # Bir karede en az bu kadar piksel değişirse hareket sayılır (640 px genişlikte).
    min_changed_pixels: int = 500
    # MOG2 arka plan modeli: kaç karelik geçmiş tutulacağı ve piksel farkı eşiği.
    history: int = 500
    var_threshold: float = 750.0
    # Programı başlattıktan sonra ortamdan uzaklaşmanız için verilen süre.
    startup_delay_seconds: int = 10
    # Toplam bu kadar saniye hareket olursa uyarı sesi + e-posta.
    warning_after_seconds: float = 2.0
    # Toplam bu kadar saniye hareket olursa kritik alarm + son işlem (kilitle/kapat).
    critical_after_seconds: float = 6.0
    # Bu kadar saniye hiç hareket olmazsa alarm seviyesi sıfırlanır.
    reset_after_quiet_seconds: float = 60.0


@dataclass
class RecordingSettings:
    directory: str = field(default_factory=lambda: str(default_recordings_dir()))
    pre_record_seconds: float = 2.0
    post_record_seconds: float = 5.0
    max_clip_seconds: float = 300.0


@dataclass
class EmailSettings:
    enabled: bool = False
    sender: str = ""
    recipients: list[str] = field(default_factory=list)
    smtp_host: str = "smtp-mail.outlook.com"
    smtp_port: int = 587
    notify_on_start: bool = True
    attach_video: bool = True
    max_attachment_mb: int = 20

    @property
    def is_complete(self) -> bool:
        return bool(self.sender and self.recipients and self.smtp_host and self.smtp_port)


@dataclass
class AppConfig:
    detection: DetectionSettings = field(default_factory=DetectionSettings)
    recording: RecordingSettings = field(default_factory=RecordingSettings)
    email: EmailSettings = field(default_factory=EmailSettings)
    final_action: FinalAction = FinalAction.LOCK
    autostart: bool = False
    # "pbkdf2_sha256$iterasyon$tuz$özet" biçiminde; düz şifre asla saklanmaz.
    admin_password_hash: str = ""

    # ---- serileştirme -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["final_action"] = self.final_action.value
        data["version"] = CONFIG_VERSION
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        try:
            final_action = FinalAction(data.get("final_action", FinalAction.LOCK.value))
        except ValueError:
            final_action = FinalAction.LOCK
        return cls(
            detection=_build(DetectionSettings, data.get("detection")),
            recording=_build(RecordingSettings, data.get("recording")),
            email=_build(EmailSettings, data.get("email")),
            final_action=final_action,
            autostart=bool(data.get("autostart", False)),
            admin_password_hash=str(data.get("admin_password_hash", "")),
        )

    # ---- dosya işlemleri ---------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        """Ayarları okur. Dosya yoksa ya da bozuksa varsayılanlarla devam eder."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Ayar dosyası bir JSON nesnesi değil")
            return cls.from_dict(data)
        except (OSError, ValueError, TypeError) as exc:
            backup = path.with_suffix(".corrupt.json")
            log.error("Ayar dosyası okunamadı (%s). Yedek: %s", exc, backup)
            try:
                os.replace(path, backup)
            except OSError:
                log.exception("Bozuk ayar dosyası yedeklenemedi")
            return cls()

    def save(self, path: Path) -> None:
        """Ayarları atomik olarak yazar (yarım kalmış dosya oluşmaz)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)


def _build(settings_cls: type, raw: Any):
    """Sözlükten dataclass üretir; bilinmeyen anahtarları yok sayar."""
    if not isinstance(raw, dict):
        return settings_cls()
    known = {f.name for f in fields(settings_cls)}
    return settings_cls(**{key: value for key, value in raw.items() if key in known})
