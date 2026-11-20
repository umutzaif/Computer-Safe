"""Koruma sırasında canlı kamera görüntüsünü ve durumu gösteren pencere."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

import cv2
import numpy as np

from computer_safe.gui.dialogs import PasswordGate
from computer_safe.mailer import Mailer
from computer_safe.monitor import MonitorState, ProtectionMonitor

POLL_INTERVAL_MS = 50
MAX_PREVIEW_WIDTH = 800


def frame_to_photo(frame: np.ndarray, max_width: int = MAX_PREVIEW_WIDTH) -> tk.PhotoImage:
    """OpenCV (BGR) karesini ek kütüphane gerektirmeden Tk görüntüsüne çevirir."""
    height, width = frame.shape[:2]
    if width > max_width:
        scale = max_width / width
        frame = cv2.resize(frame, (max_width, int(height * scale)), interpolation=cv2.INTER_AREA)
        height, width = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    ppm = f"P6 {width} {height} 255 ".encode("ascii") + rgb.tobytes()
    return tk.PhotoImage(data=ppm, format="PPM")


class MonitorWindow:
    def __init__(
        self,
        root: tk.Tk,
        monitor: ProtectionMonitor,
        mailer: Mailer,
        gate: PasswordGate,
        on_stopped: Callable[[], None],
    ):
        self._monitor = monitor
        self._mailer = mailer
        self._gate = gate
        self._on_stopped = on_stopped
        self._shown_frame: np.ndarray | None = None
        self._closed = False

        self.window = tk.Toplevel(root)
        self.window.title("Computer-Safe - Koruma aktif")
        self.window.protocol("WM_DELETE_WINDOW", self._request_stop)
        self.window.minsize(480, 400)

        self._video = ttk.Label(self.window, text="Kamera açılıyor...", anchor="center")
        self._video.pack(fill="both", expand=True, padx=8, pady=8)

        info = ttk.Frame(self.window, padding=(8, 0, 8, 8))
        info.pack(fill="x")
        self._status = ttk.Label(info, text="", font=("Segoe UI", 11, "bold"))
        self._status.pack(anchor="w")
        self._details = ttk.Label(info, text="")
        self._details.pack(anchor="w")
        self._mail = ttk.Label(info, text="", foreground="gray")
        self._mail.pack(anchor="w")
        ttk.Button(info, text="Korumayı Durdur", command=self._request_stop).pack(anchor="e", pady=(6, 0))

        self._poll()

    def _poll(self) -> None:
        if self._closed:
            return
        frame = self._monitor.latest_frame()
        if frame is not None and frame is not self._shown_frame:
            photo = frame_to_photo(frame)
            self._video.configure(image=photo, text="")
            self._video.image = photo  # referansı tut, yoksa görüntü silinir
            self._shown_frame = frame

        status = self._monitor.status
        self._status.configure(
            text=status.state.value,
            foreground="red" if status.state in (MonitorState.ALARM, MonitorState.CAMERA_ERROR) else "green",
        )
        details = f"Saldırı sayısı: {status.incidents}   Hareket süresi: {status.motion_seconds:.1f} sn"
        if status.recording:
            details += "   ● Kayıt yapılıyor"
        if status.message:
            details += f"\n{status.message}"
        self._details.configure(text=details)
        self._mail.configure(text=f"E-posta: {self._mailer.status}" if self._mailer.enabled else "E-posta bildirimi kapalı")
        self.window.after(POLL_INTERVAL_MS, self._poll)

    def _request_stop(self) -> None:
        if not self._gate.ask(self.window, "Korumayı durdur", "Korumayı durdurmak için yönetici şifresini girin:"):
            return
        self._closed = True
        self._monitor.stop()
        self._mailer.stop()
        self.window.destroy()
        self._on_stopped()
