"""Handler tests — patch the subprocess so no real transcription runs. Assert the
shape of what the handler returns, mirroring gsuite's MagicMock-the-service style.
"""

from pathlib import Path

import meeting.trans_runner as tr
from meeting.tools import build_registry

HANDLER = build_registry()["meeting_transcribe"].handler


def _fake_run(content="agreed action items", extra_ext=("srt",)):
    """Return a fake subprocess.run that writes <name>.txt (+ extras) into TRANS_DIR."""

    def fake(cmd, env=None, cwd=None, capture_output=None, text=None, timeout=None):
        out_dir = Path(env["TRANS_DIR"])
        name = cmd[2]
        (out_dir / f"{name}.txt").write_text(content, encoding="utf-8")
        for ext in extra_ext:
            (out_dir / f"{name}.{ext}").write_text(f"1\n00:00 --> 00:01\n{content}", encoding="utf-8")

        class _P:
            returncode = 0
            stdout = ""
            stderr = ""

        return _P()

    return fake


def test_transcribe_file_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "_resolve_bin", lambda name: f"/fake/{name}")
    monkeypatch.setattr(tr.subprocess, "run", _fake_run("agreed action items"))
    f = tmp_path / "meeting.m4a"
    f.write_bytes(b"x")

    res = HANDLER(input=str(f), output_dir=str(tmp_path / "out"), include=["srt"])

    assert res["ok"] is True
    assert res["engine"] == "trans"
    assert res["name"] == "meeting"
    assert "agreed action items" in res["text"]
    assert res["files"]["txt"].endswith("meeting.txt")
    assert res["extra"]["srt"].startswith("1")


def test_diarize_uses_transd(tmp_path, monkeypatch):
    seen = {}

    def fake(cmd, env=None, **kw):
        seen["cmd"] = cmd
        out_dir = Path(env["TRANS_DIR"])
        (out_dir / f"{cmd[2]}.txt").write_text("two speakers", encoding="utf-8")

        class _P:
            returncode = 0
            stdout = ""
            stderr = ""

        return _P()

    monkeypatch.setattr(tr, "_resolve_bin", lambda name: f"/fake/{name}")
    monkeypatch.setattr(tr.subprocess, "run", fake)
    f = tmp_path / "call.wav"
    f.write_bytes(b"x")

    res = HANDLER(input=str(f), diarize=True, output_dir=str(tmp_path / "o"))

    assert res["ok"] is True
    assert res["engine"] == "transd"
    assert res["name"] == "call-diarized"
    assert seen["cmd"][0].endswith("transd")


def test_missing_local_file_errors():
    res = HANDLER(input="/nope/does-not-exist.mp3")
    assert res["ok"] is False
    assert res["retryable"] is False
    assert "not found" in res["error"]


def test_blank_input_errors():
    res = HANDLER(input="   ")
    assert res["ok"] is False
    assert res["retryable"] is False


def test_text_file_passthrough(tmp_path, monkeypatch):
    # A .txt input must skip ASR entirely — no subprocess call at all.
    def boom(*a, **k):
        raise AssertionError("subprocess should not run for a text file")

    monkeypatch.setattr(tr.subprocess, "run", boom)
    f = tmp_path / "prior.txt"
    f.write_text("Cody agreed to review the deck.", encoding="utf-8")

    res = HANDLER(input=str(f))

    assert res["ok"] is True
    assert res["engine"] == "passthrough"
    assert res["text"] == "Cody agreed to review the deck."
    assert res["name"] == "prior"


def test_settings_default_drives_diarize(tmp_path, monkeypatch):
    # With diarize omitted and diarize_default=true in settings, transcribe must use transd.
    import json

    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "settings.json").write_text(json.dumps({"diarize_default": True}), encoding="utf-8")
    monkeypatch.setenv("MEETING_CONFIG_DIR", str(cfg_dir))

    seen = {}

    def fake(cmd, env=None, **kw):
        seen["bin"] = cmd[0]
        Path(env["TRANS_DIR"], f"{cmd[2]}.txt").write_text("x", encoding="utf-8")

        class _P:
            returncode = 0
            stdout = ""
            stderr = ""

        return _P()

    monkeypatch.setattr(tr, "_resolve_bin", lambda name: f"/fake/{name}")
    monkeypatch.setattr(tr.subprocess, "run", fake)
    f = tmp_path / "m.mp3"
    f.write_bytes(b"x")

    res = HANDLER(input=str(f), output_dir=str(tmp_path / "o"))

    assert res["engine"] == "transd"
    assert seen["bin"].endswith("transd")


def test_subprocess_failure_is_retryable(tmp_path, monkeypatch):
    def fail(cmd, env=None, **kw):
        class _P:
            returncode = 1
            stdout = ""
            stderr = "mlx_whisper: not found"

        return _P()

    monkeypatch.setattr(tr, "_resolve_bin", lambda name: f"/fake/{name}")
    monkeypatch.setattr(tr.subprocess, "run", fail)
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")

    res = HANDLER(input=str(f), output_dir=str(tmp_path / "out"))

    assert res["ok"] is False
    assert res["retryable"] is True
    assert "trans failed" in res["error"]
