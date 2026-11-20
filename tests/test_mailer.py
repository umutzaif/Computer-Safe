import smtplib
import socket

import pytest

from computer_safe.config import EmailSettings
from computer_safe.mailer import (
    MailJob,
    Mailer,
    PermanentMailError,
    TemporaryMailError,
    build_message,
    send_message,
)


@pytest.fixture
def settings():
    return EmailSettings(
        enabled=True, sender="gonderen@example.com", recipients=["alici@example.com"],
        smtp_host="smtp.example.com", smtp_port=587, max_attachment_mb=1,
    )


def make_mailer(settings, tmp_path, sender, online=True, password="pw"):
    return Mailer(
        settings, lambda: password, tmp_path / "outbox",
        sender=sender, connectivity_check=lambda host, port: online,
    )


def test_build_message_skips_large_and_missing_attachments(settings, tmp_path):
    small = tmp_path / "foto.jpg"
    small.write_bytes(b"x" * 100)
    big = tmp_path / "video.mp4"
    big.write_bytes(b"x" * (2 * 1024 * 1024))
    job = MailJob("Konu", "Gövde", [str(small), str(big), str(tmp_path / "yok.mp4")])

    message = build_message(settings, job)
    names = [part.get_filename() for part in message.iter_attachments()]
    assert names == ["foto.jpg"]
    body = message.get_body().get_content()
    assert "çok büyük" in body and "bulunamadı" in body


def test_offline_keeps_mail_in_outbox(settings, tmp_path):
    calls = []
    mailer = make_mailer(settings, tmp_path, lambda *a: calls.append(a), online=False)
    mailer.enqueue("Konu", "Gövde")
    assert mailer.flush() is True
    assert calls == []
    assert mailer.pending_count() == 1
    assert "Çevrimdışı" in mailer.status


def test_temporary_error_retries_later(settings, tmp_path):
    def failing(*_):
        raise TemporaryMailError("ağ yok")

    mailer = make_mailer(settings, tmp_path, failing)
    mailer.enqueue("Konu", "Gövde")
    assert mailer.flush() is True
    assert mailer.pending_count() == 1

    sent = []
    mailer._send = lambda s, p, m: sent.append(m)
    assert mailer.flush() is False
    assert mailer.pending_count() == 0
    assert "gecikmeli" in sent[0].get_body().get_content()


def test_permanent_error_moves_to_failed(settings, tmp_path):
    def failing(*_):
        raise PermanentMailError("şifre yanlış")

    mailer = make_mailer(settings, tmp_path, failing)
    mailer.enqueue("Konu", "Gövde")
    assert mailer.flush() is False
    assert mailer.pending_count() == 0
    assert len(list((tmp_path / "outbox" / "failed").glob("*.json"))) == 1


def test_missing_password_is_retried_not_dropped(settings, tmp_path):
    mailer = make_mailer(settings, tmp_path, lambda *a: None, password=None)
    mailer.enqueue("Konu", "Gövde")
    assert mailer.flush() is True
    assert mailer.pending_count() == 1


def test_disabled_mailer_ignores_jobs(settings, tmp_path):
    settings.enabled = False
    mailer = make_mailer(settings, tmp_path, lambda *a: None)
    assert mailer.enqueue("Konu", "Gövde") is None
    assert mailer.pending_count() == 0


@pytest.mark.parametrize(
    "error, expected",
    [
        (socket.gaierror(11001, "getaddrinfo failed"), TemporaryMailError),
        (TimeoutError(), TemporaryMailError),
        (ConnectionRefusedError(), TemporaryMailError),
        (smtplib.SMTPServerDisconnected(), TemporaryMailError),
        (smtplib.SMTPAuthenticationError(535, b"bad credentials"), PermanentMailError),
    ],
)
def test_send_message_classifies_errors(settings, monkeypatch, error, expected):
    def fake_smtp(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(smtplib, "SMTP", fake_smtp)
    message = build_message(settings, MailJob("Konu", "Gövde"))
    with pytest.raises(expected):
        send_message(settings, "pw", message)
