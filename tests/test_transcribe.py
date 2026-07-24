"""Handler tests — patch the subprocess so no real transcription runs. Assert the
shape of what the handler returns, mirroring gsuite's MagicMock-the-service style.

trans_runner streams the child's stdout via Popen (for live progress), so these
fakes stand in for Popen: a proc whose .stdout is an iterable of lines, plus
.wait()/.returncode. The .txt is written at launch time so the post-run read finds it.
"""

from pathlib import Path

import meeting.trans_runner as tr
from meeting.tools import build_registry

HANDLER = build_registry()["meeting_transcribe"].handler


class _FakeProc:
    def __init__(self, returncode=0, lines=()):
        self.returncode = returncode
        self.stdout = iter(lines)

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        pass

    def kill(self):
        pass


def _fake_popen(content="agreed action items", extra_ext=("srt",),
                returncode=0, lines=(), record=None):
    """Return a fake subprocess.Popen that writes <name>.txt (+ extras) into TRANS_DIR."""

    def factory(cmd, env=None, **kw):
        if record is not None:
            record["cmd"] = cmd
        if returncode == 0:
            out_dir = Path(env["TRANS_DIR"])
            name = cmd[-1]  # run_name is always the last arg (an arch prefix may lead)
            (out_dir / f"{name}.txt").write_text(content, encoding="utf-8")
            for ext in extra_ext:
                (out_dir / f"{name}.{ext}").write_text(
                    f"1\n00:00 --> 00:01\n{content}", encoding="utf-8")
        return _FakeProc(returncode, lines)

    return factory


def test_transcribe_file_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "_resolve_bin", lambda name: f"/fake/{name}")
    monkeypatch.setattr(tr.subprocess, "Popen", _fake_popen("agreed action items"))
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
    monkeypatch.setattr(tr, "_resolve_bin", lambda name: f"/fake/{name}")
    monkeypatch.setattr(tr.subprocess, "Popen",
                        _fake_popen("two speakers", extra_ext=(), record=seen))
    f = tmp_path / "call.wav"
    f.write_bytes(b"x")

    res = HANDLER(input=str(f), diarize=True, output_dir=str(tmp_path / "o"))

    assert res["ok"] is True
    assert res["engine"] == "transd"
    assert res["name"] == "call-diarized"
    assert any(str(c).endswith("transd") for c in seen["cmd"])


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
    # A .txt input must skip ASR entirely — no subprocess launch at all.
    def boom(*a, **k):
        raise AssertionError("subprocess should not run for a text file")

    monkeypatch.setattr(tr.subprocess, "Popen", boom)
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
    monkeypatch.setattr(tr, "_resolve_bin", lambda name: f"/fake/{name}")
    monkeypatch.setattr(tr.subprocess, "Popen", _fake_popen("x", extra_ext=(), record=seen))
    f = tmp_path / "m.mp3"
    f.write_bytes(b"x")

    res = HANDLER(input=str(f), output_dir=str(tmp_path / "o"))

    assert res["engine"] == "transd"
    assert any(str(c).endswith("transd") for c in seen["cmd"])


def test_subprocess_failure_is_retryable(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "_resolve_bin", lambda name: f"/fake/{name}")
    monkeypatch.setattr(tr.subprocess, "Popen",
                        _fake_popen(returncode=1, lines=["mlx_whisper: not found\n"]))
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")

    res = HANDLER(input=str(f), output_dir=str(tmp_path / "out"))

    assert res["ok"] is False
    assert res["retryable"] is True
    assert "trans failed" in res["error"]
