"""Hareket algılandığında zaman damgalı video ve fotoğraf kaydı.

Dosyalar şu düzende kaydedilir:
    <kayıt klasörü>/2026-11-20/ComputerSafe_2026-11-20_21-15-03.mp4
    <kayıt klasörü>/2026-11-20/ComputerSafe_2026-11-20_21-15-03.jpg
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

FILE_PREFIX = "ComputerSafe"
# (uzantı, codec) - ilki açılamazsa ikincisi denenir.
VIDEO_FORMATS = ((".mp4", "mp4v"), (".avi", "XVID"))


class RecorderError(Exception):
    """Kayıt dosyası oluşturulamadı (klasör yok, izin yok, disk dolu...)."""


def timestamped_path(directory: Path, suffix: str, when: datetime | None = None) -> Path:
    """Gün klasörü altında, aynı isimde dosya varsa sayaç ekleyerek benzersiz yol üretir."""
    when = when or datetime.now()
    day_dir = Path(directory) / when.strftime("%Y-%m-%d")
    try:
        day_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RecorderError(f"Kayıt klasörü oluşturulamadı: {day_dir} ({exc})") from exc

    stem = f"{FILE_PREFIX}_{when:%Y-%m-%d_%H-%M-%S}"
    path = day_dir / f"{stem}{suffix}"
    counter = 1
    while path.exists():
        path = day_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    return path


def save_snapshot(frame: np.ndarray, directory: Path) -> Path:
    """Kareyi JPEG olarak kaydeder (Türkçe karakterli klasörlerde de çalışır)."""
    path = timestamped_path(directory, ".jpg")
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RecorderError("Fotoğraf kodlanamadı")
    try:
        path.write_bytes(encoded.tobytes())
    except OSError as exc:
        raise RecorderError(f"Fotoğraf kaydedilemedi: {path} ({exc})") from exc
    return path


class VideoRecorder:
    """Hareket başlayınca kayda başlar, hareket bittikten bir süre sonra dosyayı kapatır.

    Hareketten önceki birkaç saniye de bellekte tutulup videonun başına eklenir.
    """

    def __init__(
        self,
        directory: Path,
        fps: float,
        pre_record_seconds: float = 2.0,
        post_record_seconds: float = 5.0,
        max_clip_seconds: float = 300.0,
    ):
        self.directory = Path(directory)
        self.fps = fps
        self.post_record_seconds = post_record_seconds
        self.max_clip_seconds = max_clip_seconds
        self._pre_buffer: deque[np.ndarray] = deque(maxlen=max(1, int(pre_record_seconds * fps)))
        self._writer: cv2.VideoWriter | None = None
        self._path: Path | None = None
        self._started_at = 0.0
        self._last_motion_at = 0.0

    @property
    def is_recording(self) -> bool:
        return self._writer is not None

    @property
    def current_path(self) -> Path | None:
        return self._path

    def add_frame(self, frame: np.ndarray, motion: bool, now: float) -> Path | None:
        """Kareyi işler. Bir video dosyası tamamlandıysa yolunu döndürür."""
        if self._writer is None:
            if not motion:
                self._pre_buffer.append(frame)
                return None
            self._open(frame)
            self._started_at = now
            for buffered in self._pre_buffer:
                self._writer.write(buffered)
            self._pre_buffer.clear()

        self._writer.write(frame)
        if motion:
            self._last_motion_at = now

        quiet_for = now - self._last_motion_at
        clip_length = now - self._started_at
        if quiet_for >= self.post_record_seconds or clip_length >= self.max_clip_seconds:
            return self.close()
        return None

    def close(self) -> Path | None:
        """Açık kaydı kapatır ve dosya yolunu döndürür."""
        if self._writer is None:
            return None
        self._writer.release()
        path, self._writer, self._path = self._path, None, None
        log.info("Video kaydı tamamlandı: %s", path)
        return path

    def _open(self, frame: np.ndarray) -> None:
        height, width = frame.shape[:2]
        for suffix, codec in VIDEO_FORMATS:
            path = timestamped_path(self.directory, suffix)
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), self.fps, (width, height))
            if writer.isOpened():
                self._writer, self._path = writer, path
                log.info("Video kaydı başladı: %s", path)
                return
            writer.release()
            path.unlink(missing_ok=True)
            log.warning("%s codec'i ile video açılamadı: %s", codec, path)
        raise RecorderError(f"Video dosyası oluşturulamadı: {self.directory}")
