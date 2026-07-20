from meeting.tools import build_registry


def test_transcribe_registered():
    reg = build_registry()
    assert "meeting_transcribe" in reg
    spec = reg["meeting_transcribe"]
    assert spec.input_schema["required"] == ["input"]
    props = spec.input_schema["properties"]
    assert {"input", "diarize", "model", "name", "output_dir", "include"} <= set(props)
    assert callable(spec.handler)


def test_no_duplicate_registration():
    # Importing tools twice must not double-register (decorator guards it).
    import importlib

    import meeting.tools as t

    importlib.reload(t)  # would raise ValueError on duplicate if guard failed
    assert "meeting_transcribe" in build_registry()
