import pytest


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Point settings at a throwaway dir so tests never read/write the real
    ~/.config/meeting/settings.json (and so defaults are deterministic)."""
    monkeypatch.setenv("MEETING_CONFIG_DIR", str(tmp_path / "cfg"))
