"""Görüntü üzerine durum bilgisi çizen yardımcılar.

Not: OpenCV'nin yazı fonksiyonu Türkçe karakterleri desteklemediği için buradaki
metinler ASCII olarak yazılmıştır.
"""

from __future__ import annotations

from datetime import datetime

import cv2
import numpy as np

from computer_safe.detector import BoundingBox

GREEN = (0, 200, 0)
RED = (0, 0, 255)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
YELLOW = (0, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def draw_timestamp(frame: np.ndarray, when: datetime | None = None) -> np.ndarray:
    """Sağ alt köşeye tarih-saat yazar (videoya kanıt niteliği kazandırır)."""
    text = (when or datetime.now()).strftime("%d.%m.%Y %H:%M:%S")
    height, width = frame.shape[:2]
    (text_w, text_h), baseline = cv2.getTextSize(text, FONT, 0.6, 2)
    x, y = width - text_w - 12, height - 12
    cv2.rectangle(frame, (x - 6, y - text_h - 6), (x + text_w + 6, y + baseline + 2), BLACK, -1)
    cv2.putText(frame, text, (x, y), FONT, 0.6, WHITE, 2, cv2.LINE_AA)
    return frame


def draw_status(
    frame: np.ndarray,
    *,
    alarm: bool,
    bounding_box: BoundingBox | None,
    incidents: int,
    recording: bool,
) -> np.ndarray:
    """Canlı izleme penceresi için çerçeve, durum etiketi ve sayaçları çizer."""
    height, width = frame.shape[:2]
    color = RED if alarm else GREEN

    cv2.rectangle(frame, (4, 4), (width - 5, height - 5), color, 5)
    cv2.rectangle(frame, (10, 10), (190, 50), color, -1)
    cv2.putText(frame, "ALARM" if alarm else "GUVENDE", (22, 40), FONT, 0.9, WHITE, 2, cv2.LINE_AA)

    if bounding_box is not None:
        x, y, w, h = bounding_box
        cv2.rectangle(frame, (x, y), (x + w, y + h), RED, 2)
        cv2.putText(frame, "Hareket", (x, max(20, y - 10)), FONT, 0.6, RED, 2, cv2.LINE_AA)

    if recording:
        cv2.circle(frame, (width - 70, 30), 9, RED, -1)
        cv2.putText(frame, "REC", (width - 55, 37), FONT, 0.7, RED, 2, cv2.LINE_AA)

    cv2.putText(frame, f"Saldiri sayisi: {incidents}", (14, height - 40), FONT, 0.6, color, 2, cv2.LINE_AA)
    cv2.putText(frame, "With Dalga IT", (14, height - 16), FONT, 0.5, YELLOW, 1, cv2.LINE_AA)
    return draw_timestamp(frame)


def draw_countdown(frame: np.ndarray, seconds_left: int) -> np.ndarray:
    """Koruma devreye girmeden önceki geri sayım ekranı."""
    height, width = frame.shape[:2]
    shade = frame.copy()
    cv2.rectangle(shade, (0, 0), (width, height), BLACK, -1)
    frame = cv2.addWeighted(shade, 0.45, frame, 0.55, 0)
    _centered_text(frame, "KORUMA BASLIYOR", height // 2 - 30, 1.0)
    _centered_text(frame, str(seconds_left), height // 2 + 30, 1.6)
    return frame


def _centered_text(frame: np.ndarray, text: str, y: int, scale: float) -> None:
    (text_w, _), _ = cv2.getTextSize(text, FONT, scale, 2)
    x = (frame.shape[1] - text_w) // 2
    cv2.putText(frame, text, (x, y), FONT, scale, YELLOW, 2, cv2.LINE_AA)
