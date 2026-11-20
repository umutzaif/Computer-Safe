import json

from computer_safe.config import AppConfig, FinalAction


def test_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config = AppConfig()
    config.email.sender = "a@b.com"
    config.email.recipients = ["c@d.com", "e@f.com"]
    config.final_action = FinalAction.SHUTDOWN
    config.recording.directory = str(tmp_path / "kayıtlar")
    config.save(path)

    loaded = AppConfig.load(path)
    assert loaded == config
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "password" not in json.dumps(raw["email"]).lower()


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"email": {"sender": "x@y.com", "eski_alan": 1}, "final_action": "bilinmeyen"}))
    loaded = AppConfig.load(path)
    assert loaded.email.sender == "x@y.com"
    assert loaded.final_action is FinalAction.LOCK


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{bozuk json", encoding="utf-8")
    loaded = AppConfig.load(path)
    assert loaded == AppConfig()
    assert (tmp_path / "config.corrupt.json").exists()
