"""Koruma döngüsü: kameradan kare al → hareketi algıla → kaydet → alarm ver → bildir.

Bu döngü ayrı bir iş parçacığında çalışır; arayüz yalnızca `latest_frame()` ve
`status` üzerinden okur, böylece pencere hiçbir zaman donmaz.
"""

from __future__ import annotations

import logging
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from pathlib import Path
from typing import Callable, Protocol

import cv2
import numpy as np

from computer_safe.alarm import SoundPlayer, perform_final_action
from computer_safe.config import AppConfig, FinalAction
from computer_safe.detector import MotionDetector, MotionResult
from computer_safe.mailer import Mailer
from computer_safe.overlay import draw_countdown, draw_status, draw_timestamp
from computer_safe.paths import resource_path
from computer_safe.recorder import RecorderError, VideoRecorder, save_snapshot

log = logging.getLogger(__name__)

WARNING_SOUND = "assets/alarm.wav"
CRITICAL_SOUND = "assets/lock.wav"
FINAL_ACTION_DELAY_SECONDS = 4.0      # kritik sesin duyulması için kısa bekleme
CAMERA_RETRY_SECONDS = 3.0
MAX_READ_FAILURES = 30                # art arda bu kadar kare okunamazsa kamera yeniden açılır
BEEP_FREQUENCY, BEEP_DURATION_MS = 1000, 300
MIN_FPS, MAX_FPS, FALLBACK_FPS = 5.0, 30.0, 15.0


class VideoSource(Protocol):
    def isOpened(self) -> bool: ...
    def read(self) -> tuple[bool, np.ndarray | None]: ...
    def release(self) -> None: ...


CaptureFactory = Callable[[int], VideoSource]


def open_camera(index: int) -> VideoSource:
    # DirectShow, Windows'ta varsayılan arka uca göre çok daha hızlı açılır.
    if sys.platform == "win32":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(index)


# ---------------------------------------------------------------------------
# Saldırı takibi (saf mantık - kamera/ses gerektirmez, test edilebilir)
# ---------------------------------------------------------------------------
class AlarmLevel(IntEnum):
    NONE = 0
    MOTION = 1
    WARNING = 2
    CRITICAL = 3


class TrackerEvent(Enum):
    INCIDENT_STARTED = "incident_started"
    WARNING_REACHED = "warning_reached"
    CRITICAL_REACHED = "critical_reached"
    RESET = "reset"


class IntrusionTracker:
    """Hareket sürelerini toplayıp alarm seviyesini belirler.

    - Aralarında `incident_gap` saniyeden uzun sessizlik olan hareketler ayrı
      saldırı olarak sayılır.
    - Toplam hareket süresi uyarı/kritik eşiklere ulaşınca olay üretilir.
    - Uzun süre hiç hareket olmazsa seviye sıfırlanır (saldırı sayısı korunur).
    """

    MAX_FRAME_GAP = 0.5  # takılan karelerde süre şişmesin

    def __init__(
        self,
        warning_after: float,
        critical_after: float,
        incident_gap: float = 2.0,
        reset_after_quiet: float = 60.0,
    ):
        self.warning_after = warning_after
        self.critical_after = critical_after
        self.incident_gap = incident_gap
        self.reset_after_quiet = reset_after_quiet
        self.incidents = 0
        self.motion_seconds = 0.0
        self.level = AlarmLevel.NONE
        self._last_update: float | None = None
        self._last_motion: float | None = None

    def update(self, motion: bool, now: float) -> list[TrackerEvent]:
        events: list[TrackerEvent] = []
        elapsed = 0.0 if self._last_update is None else min(now - self._last_update, self.MAX_FRAME_GAP)
        self._last_update = now

        if motion:
            if self._last_motion is None or now - self._last_motion > self.incident_gap:
                self.incidents += 1
                events.append(TrackerEvent.INCIDENT_STARTED)
            self._last_motion = now
            self.motion_seconds += elapsed
            self.level = max(self.level, AlarmLevel.MOTION)
            if self.level < AlarmLevel.WARNING and self.motion_seconds >= self.warning_after:
                self.level = AlarmLevel.WARNING
                events.append(TrackerEvent.WARNING_REACHED)
            if self.level < AlarmLevel.CRITICAL and self.motion_seconds >= self.critical_after:
                self.level = AlarmLevel.CRITICAL
                events.append(TrackerEvent.CRITICAL_REACHED)
        elif (
            self.level > AlarmLevel.NONE
            and self._last_motion is not None
            and now - self._last_motion >= self.reset_after_quiet
        ):
            self.level = AlarmLevel.NONE
            self.motion_seconds = 0.0
            events.append(TrackerEvent.RESET)
        return events


# ---------------------------------------------------------------------------
# Koruma döngüsü
# ---------------------------------------------------------------------------
class MonitorState(str, Enum):
    STARTING = "Başlatılıyor"
    ARMING = "Koruma başlıyor"
    SAFE = "Güvende"
    ALARM = "ALARM"
    CAMERA_ERROR = "Kamera hatası"
    STOPPED = "Durduruldu"


@dataclass(frozen=True)
class MonitorStatus:
    state: MonitorState = MonitorState.STARTING
    incidents: int = 0
    motion_seconds: float = 0.0
    level: AlarmLevel = AlarmLevel.NONE
    recording: bool = False
    message: str = ""


class ProtectionMonitor:
    def __init__(
        self,
        config: AppConfig,
        mailer: Mailer | None = None,
        sound: SoundPlayer | None = None,
        capture_factory: CaptureFactory = open_camera,
        clock: Callable[[], float] = time.monotonic,
        final_action: Callable[[FinalAction], None] = perform_final_action,
    ):
        self._config = config
        self._mailer = mailer
        self._sound = sound or SoundPlayer()
        self._capture_factory = capture_factory
        self._clock = clock
        self._final_action = final_action
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._last_snapshot: Path | None = None
        self.status = MonitorStatus()

    # ---- dış arayüz ---------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="monitor", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._sound.stop()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def latest_frame(self) -> np.ndarray | None:
        with self._frame_lock:
            return self._latest_frame

    # ---- ana döngü ----------------------------------------------------
    def _run(self) -> None:
        try:
            self._protect()
        except Exception:
            log.exception("Koruma döngüsü beklenmeyen bir hatayla durdu")
            self._set_status(state=MonitorState.STOPPED, message="Beklenmeyen hata - log dosyasına bakın")
            return
        self._set_status(state=MonitorState.STOPPED, message="")

    def _protect(self) -> None:
        detection = self._config.detection
        capture = self._open_camera()
        if capture is None:
            return
        detector = MotionDetector(detection.min_changed_pixels, detection.history, detection.var_threshold)
        recorder: VideoRecorder | None = None
        try:
            fps = self._arm(capture, detector)
            if fps is None:
                return
            recorder = self._make_recorder(fps)
            tracker = IntrusionTracker(
                detection.warning_after_seconds,
                detection.critical_after_seconds,
                reset_after_quiet=detection.reset_after_quiet_seconds,
            )
            self._set_status(message="")
            self._notify_started()
            log.info("Koruma aktif (kamera %d, %.1f fps)", detection.camera_index, fps)

            read_failures = 0
            while not self._stop.is_set():
                ok, frame = capture.read()
                if not ok or frame is None:
                    read_failures += 1
                    if read_failures >= MAX_READ_FAILURES:
                        log.warning("Kameradan görüntü alınamıyor, yeniden bağlanılıyor")
                        capture.release()
                        capture = self._open_camera()
                        if capture is None:
                            return
                        read_failures = 0
                    else:
                        time.sleep(0.05)
                    continue
                read_failures = 0
                recorder = self._process_frame(frame, detector, tracker, recorder)
        finally:
            if recorder is not None:
                finished = recorder.close()
                if finished:
                    self._notify_recording(finished)
            capture.release()

    def _process_frame(
        self,
        frame: np.ndarray,
        detector: MotionDetector,
        tracker: IntrusionTracker,
        recorder: VideoRecorder | None,
    ) -> VideoRecorder | None:
        now = self._clock()
        result = detector.process(frame)
        for event in tracker.update(result.detected, now):
            self._handle_event(event, frame, tracker)
        if result.detected:
            self._sound.beep(BEEP_FREQUENCY, BEEP_DURATION_MS)

        if recorder is not None:
            try:
                finished = recorder.add_frame(draw_timestamp(frame.copy()), result.detected, now)
            except RecorderError as exc:
                log.error("Video kaydı devre dışı bırakıldı: %s", exc)
                self._set_status(message=f"Video kaydedilemiyor: {exc}")
                recorder = None
            else:
                if finished:
                    self._notify_recording(finished)

        self._publish(frame, result, tracker, recorder)
        return recorder

    def _publish(
        self,
        frame: np.ndarray,
        result: MotionResult,
        tracker: IntrusionTracker,
        recorder: VideoRecorder | None,
    ) -> None:
        recording = recorder is not None and recorder.is_recording
        alarm = result.detected or tracker.level >= AlarmLevel.WARNING
        annotated = draw_status(
            frame.copy(),
            alarm=alarm,
            bounding_box=result.bounding_box,
            incidents=tracker.incidents,
            recording=recording,
        )
        self._set_frame(annotated)
        self._set_status(
            state=MonitorState.ALARM if alarm else MonitorState.SAFE,
            incidents=tracker.incidents,
            motion_seconds=tracker.motion_seconds,
            level=tracker.level,
            recording=recording,
        )

    # ---- kurulum ------------------------------------------------------
    def _open_camera(self) -> VideoSource | None:
        index = self._config.detection.camera_index
        while not self._stop.is_set():
            try:
                capture = self._capture_factory(index)
                if capture.isOpened():
                    self._set_status(state=MonitorState.STARTING, message="")
                    return capture
                capture.release()
            except cv2.error:
                log.exception("Kamera açılırken hata")
            message = f"Kamera {index} açılamadı. Bağlı mı, başka bir program kullanıyor mu?"
            log.warning(message)
            self._set_status(state=MonitorState.CAMERA_ERROR, message=message)
            self._stop.wait(CAMERA_RETRY_SECONDS)
        return None

    def _arm(self, capture: VideoSource, detector: MotionDetector) -> float | None:
        """Geri sayım yapar; bu sırada arka planı öğrenir ve kameranın FPS'ini ölçer."""
        delay = max(0, self._config.detection.startup_delay_seconds)
        started = self._clock()
        frames = 0
        last_second = None
        while not self._stop.is_set():
            elapsed = self._clock() - started
            remaining = delay - elapsed
            ok, frame = capture.read()
            if ok and frame is not None:
                frames += 1
                detector.process(frame)  # arka plan modelini eğit
                seconds_left = max(0, int(remaining) + 1)
                self._set_frame(draw_countdown(frame.copy(), seconds_left))
                self._set_status(state=MonitorState.ARMING, message=f"{seconds_left} sn içinde koruma başlıyor")
                if seconds_left != last_second and remaining > 0:
                    self._sound.beep(4000, 100)
                    last_second = seconds_left
            else:
                time.sleep(0.05)
            if remaining <= 0 and frames >= 2:
                measured = frames / max(elapsed, 1e-6)
                return min(MAX_FPS, max(MIN_FPS, measured)) if elapsed > 0.5 else FALLBACK_FPS
        return None

    def _make_recorder(self, fps: float) -> VideoRecorder | None:
        settings = self._config.recording
        if not settings.directory:
            return None
        return VideoRecorder(
            Path(settings.directory),
            fps,
            settings.pre_record_seconds,
            settings.post_record_seconds,
            settings.max_clip_seconds,
        )

    # ---- olaylar ------------------------------------------------------
    def _handle_event(self, event: TrackerEvent, frame: np.ndarray, tracker: IntrusionTracker) -> None:
        log.info("Olay: %s (saldırı sayısı %d)", event.value, tracker.incidents)
        if event is TrackerEvent.INCIDENT_STARTED:
            self._last_snapshot = self._snapshot(frame)
        elif event is TrackerEvent.WARNING_REACHED:
            self._sound.play_wav(resource_path(WARNING_SOUND))
            self._send_mail(
                "Computer-Safe: Hareket algılandı",
                f"{_now_text()} itibarıyla {_hostname()} bilgisayarının önünde hareket algılandı.\n"
                f"Saldırı sayısı: {tracker.incidents}",
                [self._last_snapshot] if self._last_snapshot else [],
            )
        elif event is TrackerEvent.CRITICAL_REACHED:
            self._sound.play_wav(resource_path(CRITICAL_SOUND))
            snapshot = self._snapshot(frame)
            action = self._config.final_action
            self._send_mail(
                "Computer-Safe: Saldırı eşiği aşıldı",
                f"{_now_text()} itibarıyla {_hostname()} bilgisayarında saldırı eşiği aşıldı.\n"
                f"Saldırı sayısı: {tracker.incidents}\n"
                f"Uygulanan işlem: {action.label}\n"
                "Video kaydı tamamlandığında ayrıca gönderilecektir.",
                [snapshot] if snapshot else [],
            )
            if action is not FinalAction.NONE:
                timer = threading.Timer(FINAL_ACTION_DELAY_SECONDS, self._final_action, args=(action,))
                timer.daemon = True
                timer.start()

    def _snapshot(self, frame: np.ndarray) -> Path | None:
        directory = self._config.recording.directory
        if not directory:
            return None
        try:
            return save_snapshot(draw_timestamp(frame.copy()), Path(directory))
        except RecorderError as exc:
            log.error("Fotoğraf kaydedilemedi: %s", exc)
            return None

    def _notify_started(self) -> None:
        if self._config.email.notify_on_start:
            self._send_mail(
                "Computer-Safe: Koruma başlatıldı",
                f"{_hostname()} bilgisayarında koruma {_now_text()} itibarıyla başlatıldı.",
            )

    def _notify_recording(self, path: Path) -> None:
        if not self._config.email.attach_video:
            return
        self._send_mail(
            "Computer-Safe: Video kaydı",
            f"{_hostname()} bilgisayarında kaydedilen video ektedir.\nDosya: {path}",
            [path],
        )

    def _send_mail(self, subject: str, body: str, attachments: list[Path] | None = None) -> None:
        if self._mailer is not None:
            self._mailer.enqueue(subject, body, attachments or [])

    # ---- durum --------------------------------------------------------
    def _set_frame(self, frame: np.ndarray) -> None:
        with self._frame_lock:
            self._latest_frame = frame

    def _set_status(self, **changes) -> None:
        current = self.status.__dict__ | changes
        self.status = MonitorStatus(**current)


def _now_text() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def _hostname() -> str:
    return socket.gethostname()
