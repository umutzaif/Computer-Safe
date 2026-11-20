import re
import time

import cv2
import numpy as np

from computer_safe.config import AppConfig, FinalAction
from computer_safe.detector import MotionDetector
from computer_safe.monitor import AlarmLevel, IntrusionTracker, MonitorState, ProtectionMonitor, TrackerEvent
from computer_safe.recorder import VideoRecorder, save_snapshot, timestamped_path


def background():
    rng = np.random.default_rng(0)
    return rng.integers(90, 110, size=(480, 640, 3), dtype=np.uint8)


def with_square(frame):
    frame = frame.copy()
    cv2.rectangle(frame, (200, 150), (360, 330), (255, 255, 255), -1)
    return frame


# ---- detector ---------------------------------------------------------------
def test_detector_finds_moving_object():
    detector = MotionDetector(min_changed_pixels=500)
    for _ in range(30):
        assert not detector.process(background()).detected
    result = detector.process(with_square(background()))
    assert result.detected
    x, y, w, h = result.bounding_box
    assert 190 <= x <= 210 and 140 <= y <= 160 and w > 100 and h > 100


def test_detector_scales_bounding_box_for_hd_frames():
    detector = MotionDetector(min_changed_pixels=500)
    hd = cv2.resize(background(), (1280, 960))
    for _ in range(30):
        detector.process(hd)
    moved = hd.copy()
    cv2.rectangle(moved, (400, 300), (720, 660), (255, 255, 255), -1)
    result = detector.process(moved)
    assert result.detected
    assert 380 <= result.bounding_box[0] <= 420


# ---- tracker ----------------------------------------------------------------
def test_tracker_escalates_and_resets():
    tracker = IntrusionTracker(warning_after=1.0, critical_after=2.0, incident_gap=2.0, reset_after_quiet=10.0)
    events = []
    t = 0.0
    for _ in range(25):  # 2.5 sn sürekli hareket
        events += tracker.update(True, t)
        t += 0.1
    assert events.count(TrackerEvent.INCIDENT_STARTED) == 1
    assert TrackerEvent.WARNING_REACHED in events
    assert TrackerEvent.CRITICAL_REACHED in events
    assert tracker.level is AlarmLevel.CRITICAL

    assert tracker.update(False, t + 5) == []
    assert tracker.update(False, t + 11) == [TrackerEvent.RESET]
    assert tracker.level is AlarmLevel.NONE

    assert tracker.update(True, t + 12) == [TrackerEvent.INCIDENT_STARTED]
    assert tracker.incidents == 2


def test_tracker_ignores_long_frame_gaps():
    tracker = IntrusionTracker(warning_after=1.0, critical_after=2.0)
    tracker.update(True, 0.0)
    tracker.update(True, 30.0)  # program 30 sn takıldı - bunu hareket sayma
    assert tracker.motion_seconds <= IntrusionTracker.MAX_FRAME_GAP


# ---- recorder ---------------------------------------------------------------
def test_timestamped_path_is_unique(tmp_path):
    first = timestamped_path(tmp_path, ".jpg")
    first.write_bytes(b"x")
    second = timestamped_path(tmp_path, ".jpg")
    assert first != second
    assert re.fullmatch(r"ComputerSafe_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(_\d+)?\.jpg", second.name)
    assert first.parent.name == second.parent.name  # gün klasörü


def test_snapshot_in_non_ascii_folder(tmp_path):
    path = save_snapshot(background(), tmp_path / "Masaüstü kayıtlar")
    assert path.exists() and path.stat().st_size > 0


def test_video_recorder_writes_clip_with_pre_and_post_roll(tmp_path):
    folder = tmp_path / "Kayıtlar ğüşiöç"
    recorder = VideoRecorder(folder, fps=10, pre_record_seconds=1, post_record_seconds=1)
    t = 0.0
    finished = None
    for i in range(60):
        motion = 20 <= i < 30
        finished = recorder.add_frame(background(), motion, t) or finished
        t += 0.1
    assert finished is not None and finished.exists()
    assert not recorder.is_recording

    capture = cv2.VideoCapture(str(finished))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    capture.release()
    # 10 kare öncesi + 10 kare hareket + ~10 kare sonrası
    assert 25 <= frame_count <= 35


# ---- monitor (sahte kamera ile uçtan uca) -----------------------------------
class FakeCamera:
    def __init__(self, frames):
        self._frames = frames
        self.released = False

    def isOpened(self):
        return True

    def read(self):
        if self._frames:
            return True, self._frames.pop(0)
        return False, None

    def release(self):
        self.released = True


class SilentSound:
    def beep(self, *a):
        pass

    def play_wav(self, path):
        self.last = path

    def stop(self):
        pass


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 0.1
        return self.now


class RecordingMailer:
    def __init__(self):
        self.subjects = []

    def enqueue(self, subject, body, attachments=()):
        self.subjects.append(subject)


def test_monitor_end_to_end(tmp_path):
    config = AppConfig()
    config.detection.startup_delay_seconds = 1
    config.detection.warning_after_seconds = 0.5
    config.detection.critical_after_seconds = 1.0
    config.recording.directory = str(tmp_path / "rec")
    config.final_action = FinalAction.LOCK

    frames = [background() for _ in range(40)] + [with_square(background()) if i % 2 else background() for i in range(30)]
    frames += [background() for _ in range(80)]
    camera = FakeCamera(frames)
    mailer = RecordingMailer()
    actions = []

    monitor = ProtectionMonitor(
        config, mailer=mailer, sound=SilentSound(), capture_factory=lambda index: camera,
        clock=FakeClock(), final_action=actions.append,
    )
    monitor.start()
    deadline = time.monotonic() + 15
    while camera._frames and time.monotonic() < deadline:
        time.sleep(0.05)
    monitor.stop()

    assert camera.released
    assert monitor.status.incidents >= 1
    assert "Computer-Safe: Koruma başlatıldı" in mailer.subjects
    assert "Computer-Safe: Hareket algılandı" in mailer.subjects
    assert "Computer-Safe: Saldırı eşiği aşıldı" in mailer.subjects
    assert "Computer-Safe: Video kaydı" in mailer.subjects
    assert list((tmp_path / "rec").rglob("*.mp4"))
    assert list((tmp_path / "rec").rglob("*.jpg"))
    assert monitor.status.state is MonitorState.STOPPED
