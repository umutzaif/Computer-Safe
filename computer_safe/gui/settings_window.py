"""Ayarlar penceresi: kayıt klasörü, e-posta, algılama ve güvenlik ayarları."""

from __future__ import annotations

import logging
import re
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from computer_safe import __version__
from computer_safe.autostart import set_autostart
from computer_safe.config import (
    SMTP_PRESETS,
    AppConfig,
    DetectionSettings,
    EmailSettings,
    FinalAction,
    RecordingSettings,
)
from computer_safe.gui.dialogs import PasswordGate, create_admin_password
from computer_safe.mailer import MailError, send_test_email
from computer_safe.security import CredentialStore, CredentialStoreError

log = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CUSTOM_PRESET = "Özel"


class ValidationError(Exception):
    """Formda hatalı ya da eksik değer var."""


class SettingsWindow:
    def __init__(
        self,
        root: tk.Tk,
        config: AppConfig,
        config_path: Path,
        credentials: CredentialStore,
        gate: PasswordGate,
        on_start: Callable[[AppConfig], None],
    ):
        self.root = root
        self.config = config
        self._config_path = config_path
        self._credentials = credentials
        self._gate = gate
        self._on_start = on_start

        root.title(f"Computer-Safe {__version__} - Ayarlar")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", root.destroy)

        self._create_variables()
        self._build()
        self._load(config)

    # ------------------------------------------------------------------
    # Form
    # ------------------------------------------------------------------
    def _create_variables(self) -> None:
        self.recordings_dir = tk.StringVar()
        self.camera_index = tk.IntVar()
        self.startup_delay = tk.IntVar()
        self.final_action = tk.StringVar()
        self.autostart = tk.BooleanVar()

        self.email_enabled = tk.BooleanVar()
        self.preset = tk.StringVar()
        self.smtp_host = tk.StringVar()
        self.smtp_port = tk.IntVar()
        self.sender = tk.StringVar()
        self.password = tk.StringVar()
        self.recipients = tk.StringVar()
        self.notify_on_start = tk.BooleanVar()
        self.attach_video = tk.BooleanVar()
        self.max_attachment_mb = tk.IntVar()

        self.min_pixels = tk.IntVar()
        self.warning_after = tk.DoubleVar()
        self.critical_after = tk.DoubleVar()
        self.pre_record = tk.DoubleVar()
        self.post_record = tk.DoubleVar()

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        self._build_general_tab(self._tab(notebook, "Genel"))
        self._build_email_tab(self._tab(notebook, "E-posta"))
        self._build_detection_tab(self._tab(notebook, "Algılama"))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Kaydet", command=self.save).pack(side="left")
        ttk.Button(buttons, text="Korumayı Başlat ▶", command=self._start).pack(side="right")
        self._status = ttk.Label(outer, text="", foreground="gray")
        self._status.pack(anchor="w", pady=(8, 0))

    @staticmethod
    def _tab(notebook: ttk.Notebook, title: str) -> ttk.Frame:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(1, weight=1)
        notebook.add(frame, text=title)
        return frame

    @staticmethod
    def _row(parent: ttk.Frame, row: int, label: str, widget: tk.Widget, hint: str = "") -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
        widget.grid(row=row, column=1, sticky="ew", pady=4)
        if hint:
            ttk.Label(parent, text=hint, foreground="gray", wraplength=420).grid(
                row=row + 1, column=1, sticky="w"
            )

    def _build_general_tab(self, tab: ttk.Frame) -> None:
        folder = ttk.Frame(tab)
        ttk.Entry(folder, textvariable=self.recordings_dir, width=46).pack(side="left", fill="x", expand=True)
        ttk.Button(folder, text="Gözat...", command=self._choose_folder).pack(side="left", padx=(6, 0))
        self._row(tab, 0, "Kayıt klasörü:", folder, "Videolar ve fotoğraflar gün klasörlerine, zaman damgasıyla kaydedilir.")

        self._row(tab, 2, "Kamera numarası:", ttk.Spinbox(tab, from_=0, to=9, textvariable=self.camera_index, width=6))
        self._row(
            tab, 3, "Başlangıç gecikmesi (sn):",
            ttk.Spinbox(tab, from_=0, to=600, textvariable=self.startup_delay, width=6),
        )
        self._row(tab, 4, "Saldırı eşiğinde:", ttk.Combobox(
            tab, textvariable=self.final_action, state="readonly", values=[a.label for a in FinalAction]
        ))
        ttk.Checkbutton(tab, text="Windows açılışında korumayı otomatik başlat", variable=self.autostart).grid(
            row=5, column=1, sticky="w", pady=4
        )
        ttk.Button(tab, text="Yönetici şifresini değiştir...", command=self._change_admin_password).grid(
            row=6, column=1, sticky="w", pady=(12, 0)
        )

    def _build_email_tab(self, tab: ttk.Frame) -> None:
        ttk.Checkbutton(tab, text="E-posta bildirimlerini etkinleştir", variable=self.email_enabled).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        preset = ttk.Combobox(tab, textvariable=self.preset, state="readonly", values=list(SMTP_PRESETS))
        preset.bind("<<ComboboxSelected>>", self._apply_preset)
        self._row(tab, 1, "E-posta servisi:", preset)
        self._row(tab, 2, "SMTP sunucusu:", ttk.Entry(tab, textvariable=self.smtp_host))
        self._row(tab, 3, "Port:", ttk.Spinbox(tab, from_=1, to=65535, textvariable=self.smtp_port, width=8))
        self._row(tab, 4, "Gönderen e-posta:", ttk.Entry(tab, textvariable=self.sender))
        self._row(
            tab, 5, "Şifre:", ttk.Entry(tab, textvariable=self.password, show="*"),
            "Gmail/Outlook için hesabınızın 'uygulama şifresi'ni kullanın. Şifre Windows Kimlik "
            "Bilgisi Yöneticisi'nde şifreli saklanır, diske düz metin yazılmaz.",
        )
        self._password_hint = ttk.Label(tab, text="", foreground="gray")
        self._password_hint.grid(row=7, column=1, sticky="w")
        self._row(
            tab, 8, "Alıcılar:", ttk.Entry(tab, textvariable=self.recipients),
            "Birden fazla adresi virgülle ayırın.",
        )
        ttk.Checkbutton(tab, text="Koruma başladığında bildir", variable=self.notify_on_start).grid(
            row=10, column=1, sticky="w"
        )
        ttk.Checkbutton(tab, text="Video kayıtlarını e-postaya ekle", variable=self.attach_video).grid(
            row=11, column=1, sticky="w"
        )
        self._row(
            tab, 12, "En büyük ek (MB):",
            ttk.Spinbox(tab, from_=1, to=50, textvariable=self.max_attachment_mb, width=6),
        )
        self._test_button = ttk.Button(tab, text="Test e-postası gönder", command=self._send_test_email)
        self._test_button.grid(row=13, column=1, sticky="w", pady=(10, 0))

    def _build_detection_tab(self, tab: ttk.Frame) -> None:
        self._row(
            tab, 0, "Hassasiyet (değişen piksel):",
            ttk.Spinbox(tab, from_=50, to=100000, increment=50, textvariable=self.min_pixels, width=8),
            "Değer küçüldükçe daha küçük hareketler algılanır. Ortamınıza göre deneyerek ayarlayın.",
        )
        self._row(
            tab, 2, "Uyarı eşiği (sn hareket):",
            ttk.Spinbox(tab, from_=0, to=600, increment=0.5, textvariable=self.warning_after, width=8),
            "Bu süre kadar hareket olunca alarm sesi çalar ve e-posta gönderilir.",
        )
        self._row(
            tab, 4, "Kritik eşik (sn hareket):",
            ttk.Spinbox(tab, from_=0, to=600, increment=0.5, textvariable=self.critical_after, width=8),
            "Bu süreye ulaşılınca 'Saldırı eşiğinde' seçeneğindeki işlem uygulanır.",
        )
        self._row(
            tab, 6, "Hareketten önce kayıt (sn):",
            ttk.Spinbox(tab, from_=0, to=10, increment=0.5, textvariable=self.pre_record, width=8),
        )
        self._row(
            tab, 7, "Hareketten sonra kayıt (sn):",
            ttk.Spinbox(tab, from_=1, to=120, increment=1, textvariable=self.post_record, width=8),
        )

    # ------------------------------------------------------------------
    # Form <-> AppConfig
    # ------------------------------------------------------------------
    def _load(self, config: AppConfig) -> None:
        self.recordings_dir.set(config.recording.directory)
        self.camera_index.set(config.detection.camera_index)
        self.startup_delay.set(config.detection.startup_delay_seconds)
        self.final_action.set(config.final_action.label)
        self.autostart.set(config.autostart)

        email = config.email
        self.email_enabled.set(email.enabled)
        self.smtp_host.set(email.smtp_host)
        self.smtp_port.set(email.smtp_port)
        self.preset.set(_preset_for(email.smtp_host, email.smtp_port))
        self.sender.set(email.sender)
        self.password.set("")
        self.recipients.set(", ".join(email.recipients))
        self.notify_on_start.set(email.notify_on_start)
        self.attach_video.set(email.attach_video)
        self.max_attachment_mb.set(email.max_attachment_mb)

        detection = config.detection
        self.min_pixels.set(detection.min_changed_pixels)
        self.warning_after.set(detection.warning_after_seconds)
        self.critical_after.set(detection.critical_after_seconds)
        self.pre_record.set(config.recording.pre_record_seconds)
        self.post_record.set(config.recording.post_record_seconds)
        self._refresh_password_hint()

    def _collect(self) -> AppConfig:
        """Formu okuyup doğrular; hatada ValidationError fırlatır."""
        try:
            directory = self.recordings_dir.get().strip()
            if not directory:
                raise ValidationError("Kayıt klasörü seçin.")
            try:
                Path(directory).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ValidationError(f"Kayıt klasörü oluşturulamadı:\n{exc}") from exc

            warning_after = float(self.warning_after.get())
            critical_after = float(self.critical_after.get())
            if critical_after < warning_after:
                raise ValidationError("Kritik eşik, uyarı eşiğinden küçük olamaz.")

            detection = replace(
                self.config.detection,
                camera_index=int(self.camera_index.get()),
                startup_delay_seconds=max(0, int(self.startup_delay.get())),
                min_changed_pixels=max(1, int(self.min_pixels.get())),
                warning_after_seconds=warning_after,
                critical_after_seconds=critical_after,
            )
            recording = replace(
                self.config.recording,
                directory=directory,
                pre_record_seconds=max(0.0, float(self.pre_record.get())),
                post_record_seconds=max(1.0, float(self.post_record.get())),
            )
            email = self._collect_email()
        except tk.TclError as exc:
            raise ValidationError("Sayısal alanlara geçerli bir sayı girin.") from exc

        action = next(a for a in FinalAction if a.label == self.final_action.get())
        return replace(
            self.config,
            detection=detection,
            recording=recording,
            email=email,
            final_action=action,
            autostart=self.autostart.get(),
        )

    def _collect_email(self) -> EmailSettings:
        sender = self.sender.get().strip()
        recipients = [r.strip() for r in self.recipients.get().replace(";", ",").split(",") if r.strip()]
        email = replace(
            self.config.email,
            enabled=self.email_enabled.get(),
            sender=sender,
            recipients=recipients,
            smtp_host=self.smtp_host.get().strip(),
            smtp_port=int(self.smtp_port.get()),
            notify_on_start=self.notify_on_start.get(),
            attach_video=self.attach_video.get(),
            max_attachment_mb=max(1, int(self.max_attachment_mb.get())),
        )
        if not email.enabled:
            return email
        if not EMAIL_PATTERN.match(sender):
            raise ValidationError("Geçerli bir gönderen e-posta adresi girin.")
        if not recipients:
            raise ValidationError("En az bir alıcı e-posta adresi girin.")
        invalid = [r for r in recipients if not EMAIL_PATTERN.match(r)]
        if invalid:
            raise ValidationError("Geçersiz alıcı adresi: " + ", ".join(invalid))
        if not email.smtp_host:
            raise ValidationError("SMTP sunucusunu girin.")
        if not 1 <= email.smtp_port <= 65535:
            raise ValidationError("Port 1-65535 arasında olmalı.")
        if not self.password.get() and not self._has_stored_password(sender):
            raise ValidationError("E-posta şifresini girin.")
        return email

    # ------------------------------------------------------------------
    # Eylemler
    # ------------------------------------------------------------------
    def save(self) -> bool:
        try:
            config = self._collect()
        except ValidationError as exc:
            messagebox.showwarning("Ayarlar", str(exc), parent=self.root)
            return False

        try:
            self._store_password(config.email.sender)
        except CredentialStoreError as exc:
            messagebox.showerror("Ayarlar", str(exc), parent=self.root)
            return False

        try:
            set_autostart(config.autostart)
        except OSError as exc:
            log.exception("Otomatik başlatma ayarlanamadı")
            messagebox.showwarning("Ayarlar", f"Otomatik başlatma ayarlanamadı:\n{exc}", parent=self.root)
            config = replace(config, autostart=False)
            self.autostart.set(False)

        try:
            config.save(self._config_path)
        except OSError as exc:
            log.exception("Ayarlar kaydedilemedi")
            messagebox.showerror("Ayarlar", f"Ayarlar kaydedilemedi:\n{exc}", parent=self.root)
            return False

        self.config = config
        self.password.set("")
        self._refresh_password_hint()
        self._status.configure(text="Ayarlar kaydedildi.")
        log.info("Ayarlar kaydedildi")
        return True

    def _store_password(self, sender: str) -> None:
        """Yeni şifre girildiyse güvenli kasaya yazar; gönderen değiştiyse eskisini siler."""
        old_sender = self.config.email.sender
        new_password = self.password.get()
        if new_password and sender:
            self._credentials.set_smtp_password(sender, new_password)
        if old_sender and old_sender.lower() != sender.lower():
            self._credentials.delete_smtp_password(old_sender)

    def _start(self) -> None:
        if self.save():
            self._on_start(self.config)

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(
            parent=self.root, initialdir=self.recordings_dir.get() or None, title="Kayıt klasörünü seçin"
        )
        if folder:
            self.recordings_dir.set(str(Path(folder)))

    def _apply_preset(self, _event: object = None) -> None:
        host, port = SMTP_PRESETS[self.preset.get()]
        if host:
            self.smtp_host.set(host)
            self.smtp_port.set(port)

    def _change_admin_password(self) -> None:
        if not self._gate.ask(self.root, "Yönetici şifresi", "Mevcut yönetici şifresini girin:"):
            return
        new_hash = create_admin_password(self.root)
        if not new_hash:
            return
        self.config = replace(self.config, admin_password_hash=new_hash)
        try:
            self.config.save(self._config_path)
        except OSError as exc:
            messagebox.showerror("Yönetici şifresi", f"Kaydedilemedi:\n{exc}", parent=self.root)
            return
        messagebox.showinfo("Yönetici şifresi", "Yönetici şifresi değiştirildi.", parent=self.root)

    def _send_test_email(self) -> None:
        try:
            email = replace(self._collect_email(), enabled=True)
            if not email.is_complete:
                raise ValidationError("Gönderen, alıcı ve sunucu bilgilerini doldurun.")
        except ValidationError as exc:
            messagebox.showwarning("Test e-postası", str(exc), parent=self.root)
            return
        except tk.TclError:
            messagebox.showwarning("Test e-postası", "Port geçerli bir sayı olmalı.", parent=self.root)
            return

        password = self.password.get() or self._stored_password(email.sender)
        if not password:
            messagebox.showwarning("Test e-postası", "E-posta şifresini girin.", parent=self.root)
            return

        self._test_button.configure(state="disabled")
        self._status.configure(text="Test e-postası gönderiliyor...")

        def worker() -> None:
            try:
                send_test_email(email, password)
                result: tuple[bool, str] = (True, "Test e-postası gönderildi. Gelen kutunuzu kontrol edin.")
            except MailError as exc:
                result = (False, str(exc))
            except Exception as exc:  # arayüzü asla çökertmesin
                log.exception("Test e-postası beklenmeyen hata")
                result = (False, f"Beklenmeyen hata: {exc}")
            self.root.after(0, self._show_test_result, *result)

        threading.Thread(target=worker, name="test-email", daemon=True).start()

    def _show_test_result(self, success: bool, message: str) -> None:
        self._test_button.configure(state="normal")
        self._status.configure(text="")
        if success:
            messagebox.showinfo("Test e-postası", message, parent=self.root)
        else:
            messagebox.showerror("Test e-postası", f"Gönderilemedi:\n{message}", parent=self.root)

    # ------------------------------------------------------------------
    # Şifre kasası yardımcıları
    # ------------------------------------------------------------------
    def _stored_password(self, sender: str) -> str | None:
        try:
            return self._credentials.get_smtp_password(sender)
        except CredentialStoreError:
            log.exception("Kayıtlı şifre okunamadı")
            return None

    def _has_stored_password(self, sender: str) -> bool:
        return bool(sender) and self._stored_password(sender) is not None

    def _refresh_password_hint(self) -> None:
        sender = self.config.email.sender
        stored = self._has_stored_password(sender)
        self._password_hint.configure(
            text="✓ Kayıtlı şifre var (değiştirmek istemiyorsanız boş bırakın)." if stored else ""
        )


def _preset_for(host: str, port: int) -> str:
    for name, (preset_host, preset_port) in SMTP_PRESETS.items():
        if preset_host and preset_host == host and preset_port == port:
            return name
    return CUSTOM_PRESET
