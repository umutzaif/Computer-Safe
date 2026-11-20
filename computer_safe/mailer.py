"""E-posta bildirimleri.

İnternet yokken uygulama çökmesin ve bildirimler kaybolmasın diye her e-posta önce
diske (outbox klasörüne) yazılır, ardından arka plandaki bir iş parçacığı göndermeyi
dener. Bağlantı yoksa e-posta kuyrukta kalır ve bağlantı gelince otomatik gönderilir.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import shutil
import smtplib
import socket
import ssl
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Callable, Iterable, Optional

from computer_safe.config import EmailSettings

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_RETRY_SECONDS = 60.0


# ---------------------------------------------------------------------------
# Hata türleri
# ---------------------------------------------------------------------------
class MailError(Exception):
    """E-posta gönderilemedi."""


class TemporaryMailError(MailError):
    """Geçici hata (internet yok, sunucu yanıt vermiyor...). Daha sonra tekrar denenir."""


class PermanentMailError(MailError):
    """Kalıcı hata (yanlış şifre, geçersiz alıcı...). Tekrar denemek işe yaramaz."""


# ---------------------------------------------------------------------------
# Mesaj oluşturma ve gönderme
# ---------------------------------------------------------------------------
@dataclass
class MailJob:
    subject: str
    body: str
    attachments: list[str] = field(default_factory=list)
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    attempts: int = 0


def build_message(settings: EmailSettings, job: MailJob) -> EmailMessage:
    """MailJob'dan e-posta oluşturur. Çok büyük ya da kayıp ekler atlanır ve gövdede belirtilir."""
    message = EmailMessage()
    message["From"] = settings.sender
    message["To"] = ", ".join(settings.recipients)
    message["Subject"] = job.subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=settings.sender.split("@")[-1] or None)

    notes: list[str] = []
    attachments: list[tuple[Path, bytes]] = []
    budget = settings.max_attachment_mb * 1024 * 1024
    for name in job.attachments:
        path = Path(name)
        try:
            size = path.stat().st_size
        except OSError:
            notes.append(f"Ek bulunamadı: {path}")
            continue
        if size > budget:
            notes.append(
                f"Ek çok büyük olduğu için eklenmedi ({size / 1048576:.1f} MB). "
                f"Bilgisayardaki konumu: {path}"
            )
            continue
        try:
            attachments.append((path, path.read_bytes()))
            budget -= size
        except OSError as exc:
            notes.append(f"Ek okunamadı ({exc}): {path}")

    if job.attempts > 0:
        notes.append(
            f"Bu bildirim {job.created_at} tarihinde oluşturuldu; bağlantı sorunu "
            "nedeniyle gecikmeli gönderildi."
        )

    body = job.body if not notes else job.body + "\n\n" + "\n".join(notes)
    message.set_content(body)

    for path, data in attachments:
        mime_type, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)
    return message


def send_message(
    settings: EmailSettings,
    password: str,
    message: EmailMessage,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """SMTP üzerinden gönderir. Tüm ağ/SMTP hatalarını MailError türlerine çevirir."""
    context = ssl.create_default_context()
    try:
        if settings.smtp_port == 465:
            client = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=timeout, context=context
            )
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
        with client:
            if settings.smtp_port != 465:
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
            client.login(settings.sender, password)
            client.send_message(message)
    # Not: smtplib hataları OSError'dan türediği için önce onlar yakalanmalı.
    except smtplib.SMTPAuthenticationError as exc:
        raise PermanentMailError(
            "E-posta adresi veya şifre hatalı. Gmail/Outlook için 'uygulama şifresi' "
            "kullanmanız gerekebilir."
        ) from exc
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
        raise PermanentMailError(f"Sunucu adresi reddetti: {exc}") from exc
    except smtplib.SMTPNotSupportedError as exc:
        raise PermanentMailError(f"Sunucu bu işlemi desteklemiyor: {exc}") from exc
    except smtplib.SMTPDataError as exc:
        if 500 <= exc.smtp_code < 600:
            raise PermanentMailError(f"Sunucu e-postayı kabul etmedi: {exc}") from exc
        raise TemporaryMailError(f"Sunucu geçici olarak hata verdi: {exc}") from exc
    except smtplib.SMTPException as exc:
        raise TemporaryMailError(f"SMTP hatası: {exc}") from exc
    except socket.gaierror as exc:
        raise TemporaryMailError(
            "İnternet bağlantısı yok ya da sunucu adı çözülemedi."
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise TemporaryMailError("Sunucu zamanında yanıt vermedi.") from exc
    except OSError as exc:  # ConnectionError, ssl.SSLError ...
        raise TemporaryMailError(f"Bağlantı hatası: {exc}") from exc


def is_online(host: str, port: int, timeout: float = 3.0) -> bool:
    """Sunucuya kısa bir TCP bağlantısı açılabiliyor mu?"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def send_test_email(settings: EmailSettings, password: str) -> None:
    """Ayarları doğrulamak için hemen bir test e-postası gönderir (MailError fırlatabilir)."""
    job = MailJob(
        subject="Computer-Safe test e-postası",
        body="Bu bir test e-postasıdır. E-posta ayarlarınız doğru çalışıyor.",
    )
    send_message(settings, password, build_message(settings, job))


# ---------------------------------------------------------------------------
# Kalıcı kuyruk + arka plan gönderici
# ---------------------------------------------------------------------------
PasswordProvider = Callable[[], Optional[str]]
Sender = Callable[[EmailSettings, str, EmailMessage], None]


class Mailer:
    """E-postaları kalıcı bir kuyruk (outbox) üzerinden arka planda gönderir."""

    def __init__(
        self,
        settings: EmailSettings,
        password_provider: PasswordProvider,
        outbox_dir: Path,
        retry_interval: float = DEFAULT_RETRY_SECONDS,
        sender: Sender = send_message,
        connectivity_check: Callable[[str, int], bool] = is_online,
    ):
        self.settings = settings
        self._password_provider = password_provider
        self._outbox = outbox_dir
        self._failed = outbox_dir / "failed"
        self._retry_interval = retry_interval
        self._send = sender
        self._is_online = connectivity_check
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._flush_lock = threading.Lock()
        self.status = "Hazır"
        self._outbox.mkdir(parents=True, exist_ok=True)

    # ---- dış arayüz ---------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self.settings.enabled and self.settings.is_complete

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="mailer", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def enqueue(self, subject: str, body: str, attachments: Iterable[Path | str] = ()) -> MailJob | None:
        """E-postayı kuyruğa ekler. İnternet olmasa bile hata vermez."""
        if not self.enabled:
            return None
        job = MailJob(subject=subject, body=body, attachments=[str(a) for a in attachments])
        try:
            self._save(job)
        except OSError:
            log.exception("E-posta kuyruğa yazılamadı: %s", subject)
            return None
        log.info("E-posta kuyruğa eklendi: %s", subject)
        self._wake.set()
        return job

    def pending_count(self) -> int:
        return len(list(self._outbox.glob("*.json")))

    def flush(self) -> bool:
        """Kuyruktaki e-postaları göndermeyi dener. Geçici hata olduysa True döner."""
        with self._flush_lock:
            for job_file in sorted(self._outbox.glob("*.json")):
                if self._stop.is_set():
                    return True
                job = self._load(job_file)
                if job is None:
                    continue
                if not self._is_online(self.settings.smtp_host, self.settings.smtp_port):
                    self.status = f"Çevrimdışı - {self.pending_count()} e-posta bekliyor"
                    log.info("İnternet yok, e-posta daha sonra gönderilecek")
                    return True
                try:
                    self._deliver(job)
                except TemporaryMailError as exc:
                    job.attempts += 1
                    self._save(job)
                    self.status = f"Gönderilemedi, tekrar denenecek: {exc}"
                    log.warning("E-posta gönderilemedi (geçici): %s", exc)
                    return True
                except PermanentMailError as exc:
                    self._move_to_failed(job_file)
                    self.status = f"E-posta hatası: {exc}"
                    log.error("E-posta gönderilemedi (kalıcı): %s", exc)
                    continue
                job_file.unlink(missing_ok=True)
                self.status = "Son e-posta gönderildi"
                log.info("E-posta gönderildi: %s", job.subject)
            return False

    # ---- iç işler -----------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            try:
                self.flush()
            except Exception:  # iş parçacığı asla ölmemeli
                log.exception("E-posta gönderici beklenmeyen bir hata aldı")
            self._wake.wait(self._retry_interval)

    def _deliver(self, job: MailJob) -> None:
        password = self._password_provider()
        if not password:
            raise TemporaryMailError("E-posta şifresi kayıtlı değil (Ayarlar > E-posta).")
        self._send(self.settings, password, build_message(self.settings, job))

    def _job_path(self, job: MailJob) -> Path:
        stamp = job.created_at.replace(":", "-")
        return self._outbox / f"{stamp}_{job.job_id}.json"

    def _save(self, job: MailJob) -> None:
        path = self._job_path(job)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(job), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _load(self, path: Path) -> MailJob | None:
        try:
            return MailJob(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            log.exception("Bozuk e-posta kuyruk dosyası: %s", path)
            self._move_to_failed(path)
            return None

    def _move_to_failed(self, path: Path) -> None:
        try:
            self._failed.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), self._failed / path.name)
        except OSError:
            log.exception("Kuyruk dosyası taşınamadı: %s", path)
