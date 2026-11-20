"""Arka plan çıkarma (MOG2) ile hareket algılama."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Algılama her zaman bu genişliğe küçültülmüş görüntüde yapılır; böylece
# hassasiyet değeri kameranın çözünürlüğünden bağımsız olur ve işlem hızlanır.
PROCESSING_WIDTH = 640
FOREGROUND_VALUE = 255  # MOG2 gölgeleri 127, gerçek hareketi 255 olarak işaretler

BoundingBox = tuple[int, int, int, int]  # x, y, genişlik, yükseklik


@dataclass(frozen=True)
class MotionResult:
    detected: bool
    changed_pixels: int
    bounding_box: BoundingBox | None = None


class MotionDetector:
    def __init__(self, min_changed_pixels: int = 500, history: int = 500, var_threshold: float = 750.0):
        self.min_changed_pixels = min_changed_pixels
        self._subtractor = cv2.createBackgroundSubtractorMOG2(history, var_threshold, True)
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    def process(self, frame: np.ndarray) -> MotionResult:
        """Kareyi arka plan modeline verir ve hareket olup olmadığını döndürür."""
        small, scale = _resize_to_width(frame, PROCESSING_WIDTH)
        mask = self._subtractor.apply(small)

        # Gölgeleri at, tek piksellik gürültüyü temizle.
        _, mask = cv2.threshold(mask, FOREGROUND_VALUE - 1, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)

        changed = int(cv2.countNonZero(mask))
        if changed < self.min_changed_pixels:
            return MotionResult(False, changed)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        box = None
        if contours:
            x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
            box = (int(x / scale), int(y / scale), int(w / scale), int(h / scale))
        return MotionResult(True, changed, box)


def _resize_to_width(frame: np.ndarray, width: int) -> tuple[np.ndarray, float]:
    height, current_width = frame.shape[:2]
    if current_width == width:
        return frame, 1.0
    scale = width / current_width
    resized = cv2.resize(frame, (width, max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
    return resized, scale
