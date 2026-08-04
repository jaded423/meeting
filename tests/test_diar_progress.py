"""Progress-mapper tests — transd stdout line in, `on_progress(phase, frac)` out.

Regression cover for the "looks hung" bug (2026-07-27): pyannote's sub-phase
counter tops out at 100% and then runs silently for minutes, so emitting a 1.0
fraction pinned the bar at 100% / ETA 0:00 on a healthy run.

The last two tests are the ones that matter beyond this file: the phase label is
a contract between `trans_runner` and the GUI's `_phase_key`, which resolves the
"STEP n OF m" counter by prefix. Relabel a phase without checking these and the
step counter silently mis-numbers.
"""

import meeting.trans_runner as tr
from meeting.assistant.gui.app import App


def _emit(line):
    """Run one stdout line through the mapper; return (phase, frac) or None."""
    calls = []
    tr._emit_transd_progress(line, lambda phase, frac: calls.append((phase, frac)))
    return calls[0] if calls else None


def test_diar_below_100_is_determinate():
    phase, frac = _emit("  [diar] segmentation 12/34 (35%)")
    assert phase == "Diarizing (segmentation)"
    assert frac == 0.35


def test_diar_at_100_goes_indeterminate_not_full():
    """frac=None, so the GUI shows a marquee and no ETA instead of 100% / 0:00."""
    phase, frac = _emit("  [diar] embeddings 34/34 (100%)")
    assert frac is None
    assert "clustering speakers" in phase


def test_segmentation_at_100_names_the_next_stage():
    phase, frac = _emit("  [diar] segmentation 34/34 (100%)")
    assert frac is None
    assert "building embeddings" in phase


def test_unknown_stage_at_100_still_indeterminate():
    """An unrecognised pyannote stage must not fall back to a pinned 100%."""
    phase, frac = _emit("  [diar] refinement 8/8 (100%)")
    assert frac is None
    assert "finishing" in phase


def test_step_key_survives_the_100pct_relabel():
    """The topped-out labels must map to the SAME step as their in-progress form."""
    assert App._phase_key("Diarizing (embeddings)") == "diar-emb"
    assert App._phase_key("Diarizing (embeddings) — clustering speakers") == "diar-emb"
    assert App._phase_key("Diarizing (segmentation)") == "diar-seg"
    assert App._phase_key("Diarizing (segmentation) — building embeddings") == "diar-seg"


def test_other_phases_unchanged():
    assert _emit("[download]  42.3% of 10MiB") == ("Downloading audio", 0.423)
    assert _emit("chunk 3/12") == ("Transcribing turn 3/12", 0.25)


def test_ensure_path_finds_tools_under_a_finder_launch(monkeypatch):
    """A Finder/LaunchServices launch inherits launchd's minimal PATH.

    Regression cover for 2026-07-28: the app reported "Claude Code isn't installed
    on this Mac" when double-clicked, because `claude` lives in ~/.local/bin, which
    is not on that PATH. `_augmented_env()` already knew the right dirs — it was
    only ever applied to child processes, never to the app's own interpreter.
    """
    import os
    import shutil

    monkeypatch.setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    assert shutil.which("claude") is None  # the bug, reproduced

    tr.ensure_path()
    for d in tr._PATH_EXTRA:
        assert d in os.environ["PATH"].split(os.pathsep)

    before = os.environ["PATH"]
    tr.ensure_path()
    assert os.environ["PATH"] == before, "ensure_path must be idempotent"


def test_hf_token_read_from_disk_when_env_is_empty(tmp_path, monkeypatch):
    """A Finder-launched app has no HF_TOKEN — it must come off disk.

    Regression cover for 2026-07-28: transd exited 1 with "HF_TOKEN required"
    because the token is a shell export and the app never sources a profile.
    """
    monkeypatch.delenv("HF_TOKEN", raising=False)
    tok_file = tmp_path / "hf_token"
    tok_file.write_text("hf_fromdisk\n")
    monkeypatch.setattr(tr, "_HF_TOKEN_FILES", [tmp_path / "missing", tok_file])

    assert tr.hf_token() == "hf_fromdisk"          # trailing newline stripped
    assert tr._augmented_env()["HF_TOKEN"] == "hf_fromdisk"


def test_env_hf_token_wins_over_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fromenv")
    tok_file = tmp_path / "hf_token"
    tok_file.write_text("hf_fromdisk")
    monkeypatch.setattr(tr, "_HF_TOKEN_FILES", [tok_file])
    assert tr.hf_token() == "hf_fromenv"


def test_no_token_anywhere_is_none_not_empty(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(tr, "_HF_TOKEN_FILES", [tmp_path / "nope"])
    assert tr.hf_token() is None
    assert "HF_TOKEN" not in tr._augmented_env()


def test_diarize_without_token_fails_early_and_actionably(monkeypatch, tmp_path):
    """No transd launch at all, and the message must name the fix."""
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(tr, "_HF_TOKEN_FILES", [tmp_path / "nope"])

    def _boom(*a, **k):
        raise AssertionError("transd must not launch without a token")

    monkeypatch.setattr(tr.subprocess, "Popen", _boom)
    try:
        tr.run("/tmp/x.m4a", diarize=True)
    except tr.TransError as exc:
        assert "hf.co/settings/tokens" in str(exc)
    else:
        raise AssertionError("expected TransError")


def test_error_tail_strips_ansi():
    """transd colours its errors; raw escapes landed in the GUI dialog."""
    assert tr._ANSI.sub("", "\x1b[0;31mHF_TOKEN required\x1b[0m") == "HF_TOKEN required"
