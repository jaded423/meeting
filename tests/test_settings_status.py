import json

from meeting import settings
from meeting.tools import build_registry
from meeting.tools.status_tools import status


def test_defaults_when_no_file():
    s = settings.load_settings()
    assert s.diarize_default is False
    assert s.approval_gate is True
    assert s.default_model == "small"


def test_write_default_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MEETING_CONFIG_DIR", str(tmp_path / "cfg"))
    p = settings.write_default_settings()
    assert p.is_file()
    assert json.loads(p.read_text())["approval_gate"] is True

    # write_default_settings must NOT clobber an existing file
    p.write_text(json.dumps({"approval_gate": False, "diarize_default": True}), encoding="utf-8")
    settings.write_default_settings()
    s = settings.load_settings()
    assert s.approval_gate is False
    assert s.diarize_default is True


def test_malformed_settings_falls_back(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "settings.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.setenv("MEETING_CONFIG_DIR", str(cfg))
    s = settings.load_settings()  # must not raise
    assert s.approval_gate is True


def test_status_registered_and_shape():
    assert "meeting_status" in build_registry()
    out = status()
    assert out["ok"] is True
    assert set(out["engines"]) == {"trans", "transd", "mlx_whisper", "yt_dlp"}
    assert set(out["settings"]) >= {"diarize_default", "approval_gate", "config_file"}
    assert "diarize_default" in out["how_to_change"]
    assert isinstance(out["ready"], bool)
