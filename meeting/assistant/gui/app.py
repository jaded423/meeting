"""Meeting Assistant — the native macOS GUI.

A thin Tk front-end over the two organs already built: ``transcribe.transcribe()``
(local Whisper, with a progress callback) and the ``brain`` (headless ``claude -p``).
Three states in one window, matching the approved mockup:

  1. Set up & transcribe — pick a file / URL / pasted text; choose quality
     (Fast / Balanced / Best), speaker labels, and account; press Transcribe.
  2. Working — progress bar + ETA (determinate for Whisper, marquee for the
     diarize path / model download) + Cancel.
  3. Review & confirm — every proposed item editable (owner / action / date /
     Event-vs-Task) with an invite-chip list you eyeball before anything sends.
     Nothing is created until you press "Create N items".

Run for local testing:  python -m meeting.assistant.gui
"""

from __future__ import annotations

import logging
import os
import queue
import re
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

# --- frozen (.app) resource + path handling; harmless when run from source ----
if getattr(sys, "frozen", False):  # PyInstaller bundle
    sys.path.insert(0, sys._MEIPASS)  # type: ignore[attr-defined]

from ... import trans_runner  # noqa: E402
from .. import brain, contacts, transcribe  # noqa: E402
from .worker import CreateWorker, EmailWorker, TranscribeWorker  # noqa: E402

# --- logging: a --windowed .app has no console, so this is the only debug channel
_LOG_DIR = Path.home() / "Library" / "Logs" / "MeetingAssistant"


def setup_logging() -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(_LOG_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
    except OSError:
        pass


log = logging.getLogger("meeting-assistant")

# Quality tiers → (label, whisper model, realtime factor for the ETA estimate).
# Factors are rough Apple-Silicon mlx ratios (elapsed ≈ audio_seconds × factor).
MODELS = [
    ("Fast", "small", 0.10),
    ("Balanced", "medium", 0.25),
    ("Best", "large-v3", 0.62),
]
DEFAULT_OUT = Path.home() / "projects" / "trans" / "transcriptions"
PAD = 14

# Time-of-day picker for an event row. A dated commitment usually arrives with no
# stated time, and an all-day event renders as a 24-hour busy bar most people
# scroll past — so a real morning slot is the default and "All day" is an explicit
# choice. Half-hour slots across a working day cover everything a meeting produces.
ALL_DAY = "All day"
DEFAULT_TIME = "9:00 AM"
TIMES = [ALL_DAY] + [
    f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    for h in range(7, 19)
    for m in (0, 30)
]


def _split_when(value: str) -> tuple[str, str]:
    """A model-supplied "date" -> (YYYY-MM-DD, picker label).

    No time in the string means the model didn't hear one — that's the 9:00 AM
    default, not an all-day event.
    """
    value = (value or "").strip()
    if not value:
        return "", DEFAULT_TIME
    parts = value.replace("T", " ").split()
    day = parts[0]
    if len(parts) < 2:
        return day, DEFAULT_TIME
    try:
        label = datetime.strptime(parts[1][:5], "%H:%M").strftime("%-I:%M %p")
    except ValueError:
        return day, DEFAULT_TIME
    return day, label if label in TIMES else DEFAULT_TIME


def _join_when(day: str, label: str) -> str | None:
    """(date, picker label) -> what gsuite's `start` wants, or None if undated.

    `YYYY-MM-DD` is an all-day event to `calendar_create_event`; `YYYY-MM-DD HH:MM`
    is a timed one. Neither needs a timezone — the tool stamps the calendar's own.
    """
    day = (day or "").strip()
    if not day:
        return None
    if label == ALL_DAY:
        return day
    try:
        return f"{day} {datetime.strptime(label, '%I:%M %p').strftime('%H:%M')}"
    except ValueError:
        return day


def _dark_mode() -> bool:
    try:
        out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                             capture_output=True, text=True, timeout=3)
        return "dark" in (out.stdout or "").lower()
    except (OSError, subprocess.SubprocessError):
        return False


# Theme-aware text colors — hardcoded light greys were invisible on dark mode.
_DARK = _dark_mode()
MUTED = "#9BA1AC" if _DARK else "#5B616E"   # secondary labels
FAINT = "#7A808B" if _DARK else "#9AA0AC"   # tertiary / placeholders
OK = "#2BBB90" if _DARK else "#0E8C6B"      # "nothing sent" / done
WARN = "#E0A552" if _DARK else "#A9660C"    # ambiguity / no-email
CHIP = "#C9CDD4" if _DARK else "#333333"    # known-email guest chip

# coverage-ledger status glyphs (topic was captured / needed nothing / was dropped)
GLYPH = {"covered": "✓", "no-action": "·", "missed": "⚠"}


def _fmt(sec: float | None) -> str:
    if sec is None:
        return "—"
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _notify(title: str, message: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}"'],
            check=False, capture_output=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Meeting Assistant")
        root.minsize(720, 560)

        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self.worker: TranscribeWorker | None = None
        self.create_worker: CreateWorker | None = None

        # setup state
        self.mode = tk.StringVar(value="file")       # file | url | text
        self.model = tk.StringVar(value="medium")    # whisper model
        self.diarize = tk.BooleanVar(value=True)
        self.audit = tk.BooleanVar(value=True)       # second-pass completeness check
        self.account = tk.StringVar(value=contacts.accounts()[0])
        self.input_var = tk.StringVar()
        self.meeting_date = tk.StringVar(value=date.today().isoformat())
        self._audio_seconds: float | None = None
        self._text_widget: tk.Text | None = None

        # review state
        self.transcript = ""
        self.rows: list[dict] = []
        self.coverage: dict = {"topics": [], "missed": []}
        # Opt-out, not opt-in: the audit email is the only artifact that survives a
        # wrong extraction — it carries the transcript AND the skipped rows, which
        # Calendar can never tell you about. So the safe state is the default state.
        self.email_on_create = tk.BooleanVar(value=True)
        self.email_to = tk.StringVar(value="")

        self._build_header()
        self.body = ttk.Frame(root, padding=PAD)
        self.body.pack(fill="both", expand=True)
        self.show_setup()

        root.after(150, self._poll)

    # ---------------------------------------------------------------- header
    def _build_header(self) -> None:
        bar = ttk.Frame(self.root, padding=(PAD, 10))
        bar.pack(fill="x")
        ttk.Label(bar, text="Meeting Assistant",
                  font=("", 15, "bold")).pack(side="left")
        self.subtitle = ttk.Label(bar, text="Local transcription · nothing sent until you confirm",
                                   foreground=MUTED)
        self.subtitle.pack(side="left", padx=10)
        ttk.Separator(self.root, orient="horizontal").pack(fill="x")

    def _clear_body(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()

    # ---------------------------------------------------------------- setup
    def show_setup(self) -> None:
        self._clear_body()
        self._text_widget = None

        # input mode tabs
        modes = ttk.Frame(self.body)
        modes.pack(fill="x", pady=(0, 8))
        ttk.Label(modes, text="INPUT", foreground=MUTED).pack(side="left", padx=(0, 10))
        for val, label in (("file", "Audio / Video"), ("url", "Paste URL"), ("text", "Paste transcript")):
            ttk.Radiobutton(modes, text=label, value=val, variable=self.mode,
                            command=self._render_input).pack(side="left", padx=4)

        self.input_frame = ttk.Frame(self.body)
        self.input_frame.pack(fill="both", pady=(0, 14))
        self._render_input()

        # controls row
        controls = ttk.Frame(self.body)
        controls.pack(fill="x", pady=(4, 0))

        qwrap = ttk.Frame(controls)
        qwrap.grid(row=0, column=0, sticky="nw", padx=(0, 28))
        ttk.Label(qwrap, text="QUALITY", foreground=MUTED).pack(anchor="w", pady=(0, 4))
        seg = ttk.Frame(qwrap)
        seg.pack(anchor="w")
        self._eta_labels: dict[str, tk.StringVar] = {}
        for label, model, _factor in MODELS:
            cell = ttk.Frame(seg)
            cell.pack(side="left", padx=2)
            tk.Radiobutton(cell, text=label, value=model, variable=self.model,
                           indicatoron=0, width=9, padx=6, pady=4).pack()
            eta = tk.StringVar(value="")
            self._eta_labels[model] = eta
            ttk.Label(cell, textvariable=eta, foreground=MUTED).pack()
        self._refresh_eta()

        dwrap = ttk.Frame(controls)
        dwrap.grid(row=0, column=1, sticky="nw", padx=(0, 28))
        ttk.Label(dwrap, text="SPEAKER LABELS", foreground=MUTED).pack(anchor="w", pady=(0, 4))
        ttk.Checkbutton(dwrap, text="Label who said what",
                        variable=self.diarize).pack(anchor="w")
        ttk.Label(dwrap, text="needed to route items per person",
                  foreground=MUTED).pack(anchor="w")
        ttk.Checkbutton(dwrap, text="Double-check for missed items",
                        variable=self.audit).pack(anchor="w", pady=(8, 0))
        ttk.Label(dwrap, text="second pass — costs ~1 min, catches drops",
                  foreground=MUTED).pack(anchor="w")

        awrap = ttk.Frame(controls)
        awrap.grid(row=0, column=2, sticky="nw")
        ttk.Label(awrap, text="ACCOUNT", foreground=MUTED).pack(anchor="w", pady=(0, 4))
        ttk.Combobox(awrap, textvariable=self.account, values=contacts.accounts(),
                     state="readonly", width=14).pack(anchor="w")
        ttk.Button(awrap, text="Manage guests…", command=self._manage_contacts).pack(anchor="w", pady=(6, 0))

        mwrap = ttk.Frame(controls)
        mwrap.grid(row=0, column=3, sticky="nw", padx=(28, 0))
        ttk.Label(mwrap, text="MEETING DATE", foreground=MUTED).pack(anchor="w", pady=(0, 4))
        ttk.Entry(mwrap, textvariable=self.meeting_date, width=13).pack(anchor="w")
        ttk.Label(mwrap, text='anchors "this Friday" etc.', foreground=MUTED).pack(anchor="w")

        # footer
        ttk.Separator(self.body, orient="horizontal").pack(fill="x", pady=16)
        foot = ttk.Frame(self.body)
        foot.pack(fill="x")
        ttk.Label(foot, text="Runs locally on this Mac — nothing is uploaded.",
                  foreground=MUTED).pack(side="left")
        ttk.Button(foot, text="Transcribe →", command=self._start).pack(side="right")

    def _manage_contacts(self) -> None:
        from .contacts_dialog import ContactsManager
        ContactsManager(self.root, self.account.get())

    def _render_input(self) -> None:
        for w in self.input_frame.winfo_children():
            w.destroy()
        self._text_widget = None
        mode = self.mode.get()

        if mode == "text":
            self._text_widget = tk.Text(self.input_frame, height=8, wrap="word")
            self._text_widget.pack(fill="both", expand=True)
            self._text_widget.insert("1.0", "")
            self._audio_seconds = None
            self._refresh_eta()
            return

        row = ttk.Frame(self.input_frame)
        row.pack(fill="x")
        entry = ttk.Entry(row, textvariable=self.input_var)
        entry.pack(side="left", fill="x", expand=True)
        if mode == "file":
            ttk.Button(row, text="Browse…", command=self._browse).pack(side="left", padx=(8, 0))
        else:  # url
            self._audio_seconds = None
            self._refresh_eta()

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose a meeting recording",
            filetypes=[("Media", "*.m4a *.mp3 *.wav *.mp4 *.mov *.aac *.flac"),
                       ("Text", "*.txt *.md *.srt *.vtt"), ("All", "*.*")],
        )
        if not path:
            return
        self.input_var.set(path)
        try:
            self._audio_seconds = transcribe._duration(path)
        except Exception:  # noqa: BLE001
            self._audio_seconds = None
        try:  # best-effort meeting-date guess from the file's mtime
            self.meeting_date.set(date.fromtimestamp(os.path.getmtime(path)).isoformat())
        except OSError:
            pass
        self._refresh_eta()

    def _refresh_eta(self) -> None:
        if not hasattr(self, "_eta_labels"):
            return
        for label, model, factor in MODELS:
            if self._audio_seconds:
                self._eta_labels[model].set(f"~{_fmt(self._audio_seconds * factor)}")
            else:
                hint = {"small": "fastest", "medium": "balanced", "large-v3": "most accurate"}
                self._eta_labels[model].set(hint.get(model, ""))

    def _resolve_input(self) -> str | None:
        """Return a file path or URL to hand the transcriber (writing a temp file for pasted text)."""
        mode = self.mode.get()
        if mode == "text":
            content = self._text_widget.get("1.0", "end").strip() if self._text_widget else ""
            if not content:
                messagebox.showwarning("No transcript", "Paste a transcript first.")
                return None
            tmp = Path(tempfile.gettempdir()) / f"meeting-paste-{datetime.now():%Y%m%d-%H%M%S}.txt"
            tmp.write_text(content, encoding="utf-8")
            return str(tmp)
        value = self.input_var.get().strip()
        if not value:
            messagebox.showwarning("No input", "Choose a file or paste a URL first.")
            return None
        if mode == "file" and not Path(value).expanduser().is_file():
            messagebox.showerror("File not found", f"No file at:\n{value}")
            return None
        return value

    def _derive_name(self, s: str) -> str:
        p = Path(s)
        base = p.stem if p.exists() else s.rstrip("/").rsplit("/", 1)[-1]
        slug = "".join(c if c.isalnum() else "-" for c in base).strip("-")
        return slug[:40] or "meeting"

    # -------------------------------------------------------------- progress
    def _start(self) -> None:
        resolved = self._resolve_input()
        if not resolved:
            return
        params = {
            "input": resolved,
            "name": self._derive_name(resolved),
            "out_dir": str(DEFAULT_OUT),
            "model": self.model.get(),
            "diarize": bool(self.diarize.get()),
            "audit": bool(self.audit.get()),
            "account": self.account.get(),
            "meeting_date": self.meeting_date.get().strip(),
        }
        self._phase_label = None  # reset ETA phase tracking for this run
        self._run_name = params["name"]
        self._is_url = "://" in resolved
        self._is_text = (not self._is_url) and Path(resolved).suffix.lower() in {
            ".txt", ".md", ".srt", ".vtt", ".tsv"}
        self._run_diarize = bool(self.diarize.get())
        self._run_audit = bool(self.audit.get())
        self._steps = self._compute_steps()
        log.info("start: %s (steps=%s)", {k: v for k, v in params.items() if k != "input"}, self._steps)
        self.worker = TranscribeWorker(params, self.queue)
        self.show_progress()
        self.worker.start()

    def show_progress(self) -> None:
        self._clear_body()
        wrap = ttk.Frame(self.body)
        wrap.pack(fill="both", expand=True)

        self.prog_step = ttk.Label(wrap, text="", foreground=MUTED)
        self.prog_step.pack(anchor="w", pady=(30, 0))
        self.prog_status = ttk.Label(wrap, text="Starting…", font=("", 13, "bold"))
        self.prog_status.pack(anchor="w", pady=(0, 4))
        self.prog_nums = ttk.Label(wrap, text="", foreground=MUTED)
        self.prog_nums.pack(anchor="w", pady=(0, 14))

        self.pbar = ttk.Progressbar(wrap, mode="indeterminate", length=520)
        self.pbar.pack(anchor="w")
        self.pbar.start(12)
        self.prog_eta = ttk.Label(wrap, text="", foreground=MUTED)
        self.prog_eta.pack(anchor="w", pady=(8, 0))
        # Wall-clock that ticks every second — reassures during opaque steps
        # (e.g. pyannote diarization) that emit no live progress of their own.
        self.prog_total = ttk.Label(wrap, text="", foreground=MUTED)
        self.prog_total.pack(anchor="w", pady=(2, 0))

        ttk.Label(wrap, text="Runs on-device — you can walk away; "
                             "you'll get a notification when it's ready.",
                  foreground=MUTED).pack(anchor="w", pady=(24, 0))
        ttk.Button(wrap, text="Cancel", command=self._cancel).pack(anchor="w", pady=(20, 0))

        self._run_t0 = time.monotonic()
        self._tick()

    def _tick(self) -> None:
        """Update the always-running wall-clock while the progress screen is up."""
        try:
            if not self.prog_total.winfo_exists():
                return
        except (AttributeError, tk.TclError):
            return
        elapsed = time.monotonic() - getattr(self, "_run_t0", time.monotonic())
        self.prog_total.config(text=f"total elapsed {_fmt(elapsed)}")
        self.root.after(1000, self._tick)

    def _cancel(self) -> None:
        if self.worker and self.worker.is_alive():
            self.worker.cancel()
            self.prog_status.config(text="Cancelling…")

    def _set_determinate(self) -> None:
        if str(self.pbar["mode"]) != "determinate":
            self.pbar.stop()
            self.pbar.config(mode="determinate", maximum=100.0)

    def _set_indeterminate(self) -> None:
        if str(self.pbar["mode"]) != "indeterminate":
            self.pbar.config(mode="indeterminate", value=0)
            self.pbar.start(12)

    # --- overall "Step N of M" tracking --------------------------------------
    # The pipeline's stages depend on the run: URL adds a download; diarization
    # adds segmentation + embeddings; a text transcript skips ASR entirely. We
    # build the expected ordered list at start and map each live phase into it.
    def _compute_steps(self) -> list[str]:
        steps: list[str] = []
        if self._is_url:
            steps.append("download")
        if not self._is_text:
            if self._run_diarize:
                steps += ["diar-seg", "diar-emb", "transcribe"]
            else:
                steps.append("transcribe")
        steps.append("analyze")
        if getattr(self, "_run_audit", False):
            steps.append("audit")
        return steps

    @staticmethod
    def _phase_key(phase: str) -> str | None:
        if phase.startswith("Downloading"):
            return "download"
        if phase.startswith("Diarizing (embeddings"):
            return "diar-emb"
        if phase.startswith("Diarizing"):
            return "diar-seg"
        if phase.startswith("Transcribing"):
            return "transcribe"
        if phase.startswith("Double-checking"):
            return "audit"
        if phase.startswith(("Reading", "Analyzing")):
            return "analyze"
        return None

    def _update_step(self, phase: str) -> None:
        key = self._phase_key(phase)
        steps = getattr(self, "_steps", [])
        if key and steps and key in steps:
            self.prog_step.config(text=f"STEP {steps.index(key) + 1} OF {len(steps)}")

    # ---------------------------------------------------------------- review
    def show_review(self, items: list[dict], transcript: str, meta: dict,
                    coverage: dict | None = None) -> None:
        self.transcript = transcript
        self.coverage = coverage or {"topics": [], "missed": []}
        self._meta = meta
        self._clear_body()
        self.rows = []
        account = self.account.get()
        if not self.email_to.get():
            self.email_to.set(contacts.me(account).get("email", ""))

        recap = ttk.Frame(self.body)
        recap.pack(fill="x", pady=(0, 8))
        ttk.Label(recap, text=(f"{meta.get('words', 0):,} words · {meta.get('engine', '')}"
                               f" · {_fmt(meta.get('seconds'))}"),
                  foreground=MUTED).pack(side="left")
        ttk.Label(recap, text="  ● Nothing sent yet", foreground=OK).pack(side="right")

        # Second-pass candidates ride in the same list as the first pass, but always
        # unchecked and tagged — you opt them IN, you never have to spot them.
        flagged = [dict(m, _flagged=True) for m in (self.coverage.get("missed") or [])]
        merged = [dict(it, _flagged=False) for it in items] + flagged
        self._build_coverage(len(merged))

        ttk.Label(self.body,
                  text="Edit anything, uncheck to skip, add or remove guests before you create them:",
                  foreground=MUTED).pack(anchor="w", pady=(0, 8))

        # scrollable list
        outer = ttk.Frame(self.body)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vs = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", width=1)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(canvas.find_all()[0], width=e.width))
        canvas.configure(yscrollcommand=vs.set)
        canvas.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 3)), "units"))

        me_name = contacts.me(account).get("name", "")
        for item in merged:
            self._build_row(inner, item, account, me_name)

        # footer
        ttk.Separator(self.body, orient="horizontal").pack(fill="x", pady=12)

        mail = ttk.Frame(self.body)
        mail.pack(fill="x", pady=(0, 8))
        # One send path only. This rides along with the Create action below rather
        # than getting its own button — a separate "send now" meant pressing both
        # mailed the same report twice.
        ttk.Checkbutton(mail, text="Email transcript + this report to",
                        variable=self.email_on_create,
                        command=self._refresh_count).pack(side="left")
        ttk.Entry(mail, textvariable=self.email_to, width=32).pack(side="left", padx=6)
        self.mail_status = ttk.Label(
            mail, text="sent once, with the items below", foreground=MUTED)
        self.mail_status.pack(side="left", padx=8)

        foot = ttk.Frame(self.body)
        foot.pack(fill="x")
        self.count_lbl = ttk.Label(foot, text="", foreground=MUTED)
        self.count_lbl.pack(side="left")
        self.create_btn = ttk.Button(foot, text="Create selected →", command=self._create)
        self.create_btn.pack(side="right")
        ttk.Button(foot, text="Export transcript", command=self._export).pack(side="right", padx=8)
        ttk.Button(foot, text="← Start over", command=self.show_setup).pack(side="left", padx=12)
        self._refresh_count()

    def _build_coverage(self, n_items: int) -> None:
        """The 'did we get everything?' header — topic ledger from the second pass.

        The point is to make under-inclusion VISIBLE: "9 topics → 4 items" is a
        question worth asking, and you cannot ask it if all you ever see is the
        4 items the brain chose to show you.
        """
        topics = self.coverage.get("topics") or []
        if not topics:
            return
        n_missed = sum(1 for t in topics if t.get("status") == "missed")
        speakers = len(set(re.findall(r"\[SPEAKER_\d+\]", self.transcript)))

        bar = ttk.Frame(self.body)
        bar.pack(fill="x", pady=(0, 6))
        bits = [f"{len(topics)} topics", f"{n_items} items"]
        if speakers:
            bits.insert(0, f"{speakers} speakers")
        ttk.Label(bar, text="COVERAGE", foreground=MUTED).pack(side="left", padx=(0, 8))
        ttk.Label(bar, text=" · ".join(bits)).pack(side="left")
        if n_missed:
            ttk.Label(bar, text=f"  ⚠ {n_missed} the first pass missed",
                      foreground=WARN).pack(side="left")

        self._topics_frame = ttk.Frame(self.body)
        self._topics_shown = False
        toggle = ttk.Button(bar, text="Show topics ▾")

        def _toggle() -> None:
            self._topics_shown = not self._topics_shown
            if self._topics_shown:
                self._topics_frame.pack(fill="x", pady=(0, 8), before=self._topics_anchor)
                toggle.config(text="Hide topics ▴")
            else:
                self._topics_frame.pack_forget()
                toggle.config(text="Show topics ▾")

        toggle.config(command=_toggle)
        toggle.pack(side="right")
        self._topics_anchor = ttk.Frame(self.body)  # keeps the list above the rows
        self._topics_anchor.pack(fill="x")

        for t in topics:
            status = t.get("status", "no-action")
            note = f" — {t['note']}" if t.get("note") else ""
            fg = WARN if status == "missed" else (MUTED if status == "no-action" else CHIP)
            ttk.Label(self._topics_frame,
                      text=f"  {GLYPH.get(status, '·')} {t.get('topic', '')}{note}",
                      foreground=fg).pack(anchor="w")

    def _build_row(self, parent, item: dict, account: str, me_name: str) -> None:
        owner = str(item.get("owner", "") or "unassigned")
        participants = [p for p in (item.get("participants") or []) if p]
        invitees = []
        for name in participants:
            invitees.append({"name": name, "email": contacts.resolve(name, account) or ""})

        row = ttk.Frame(parent, padding=(6, 8))
        row.pack(fill="x", pady=3)
        ttk.Separator(parent, orient="horizontal").pack(fill="x")

        top = ttk.Frame(row)
        top.pack(fill="x")

        flagged = bool(item.get("_flagged"))
        # a second-pass candidate is a suggestion, not a finding — never pre-checked
        include = tk.BooleanVar(value=not flagged and not bool(item.get("ambiguous")))
        ttk.Checkbutton(top, variable=include, command=self._refresh_count).pack(side="left")

        owner_lbl = owner + ("  · you" if owner.lower() == me_name.lower() and me_name else "")
        ttk.Label(top, text=owner_lbl, width=22, foreground=MUTED).pack(side="left", padx=(4, 8))

        action_var = tk.StringVar(value=str(item.get("action", "")))
        ttk.Entry(top, textvariable=action_var).pack(side="left", fill="x", expand=True)

        day, time_label = _split_when(str(item.get("date") or ""))
        date_var = tk.StringVar(value=day)
        date_entry = ttk.Entry(top, textvariable=date_var, width=11)
        date_entry.pack(side="left", padx=(6, 3))

        time_var = tk.StringVar(value=time_label)
        time_cb = ttk.Combobox(top, textvariable=time_var, values=TIMES,
                               state="readonly", width=9)
        time_cb.pack(side="left", padx=(0, 6))

        type_var = tk.StringVar(value=str(item.get("type", "event")))
        ttk.Combobox(top, textvariable=type_var, values=["event", "task"],
                     state="readonly", width=7).pack(side="left")

        inv_frame = ttk.Frame(row)
        inv_frame.pack(fill="x", pady=(6, 0), padx=(28, 0))

        record = {
            "include": include, "action": action_var, "date": date_var,
            "time": time_var, "type": type_var, "invitees": invitees,
            "inv_frame": inv_frame, "ambiguous": item.get("ambiguous"),
            "owner": owner, "flagged": flagged,
            "date_entry": date_entry, "time_cb": time_cb,
        }
        self.rows.append(record)
        self._render_invitees(record)

        # An event with no date is impossible to create (Calendar needs a start),
        # so re-validate live as either field is edited. The time picker only
        # applies to events — Tasks honour the date and ignore any time — so it
        # greys out rather than lying about what will happen.
        date_var.trace_add("write", lambda *_: self._refresh_count())
        type_var.trace_add("write", lambda *_: self._sync_time_state(record))
        self._sync_time_state(record)

        if flagged:
            ttk.Label(row, text="⊕ 2nd pass — the first read dropped this; check it to include",
                      foreground=WARN).pack(anchor="w", padx=(28, 0))
        if item.get("ambiguous"):
            ttk.Label(row, text=f"⚠ {item['ambiguous']}", foreground=WARN).pack(anchor="w", padx=(28, 0))

    def _render_invitees(self, record: dict) -> None:
        frame = record["inv_frame"]
        for w in frame.winfo_children():
            w.destroy()
        ttk.Label(frame, text="Invite:", foreground=MUTED).pack(side="left", padx=(0, 6))
        if not record["invitees"]:
            ttk.Label(frame, text="(no guests)", foreground=FAINT).pack(side="left")
        for inv in list(record["invitees"]):
            chip = ttk.Frame(frame)
            chip.pack(side="left", padx=3)
            txt = inv["name"] + ("" if inv["email"] else "  (no email)")
            fg = CHIP if inv["email"] else WARN
            ttk.Label(chip, text=txt, foreground=fg).pack(side="left")
            ttk.Button(chip, text="✕", width=2,
                       command=lambda r=record, i=inv: self._remove_guest(r, i)).pack(side="left")
        ttk.Button(frame, text="+ guest", command=lambda r=record: self._add_guest(r)).pack(side="left", padx=4)

    def _add_guest(self, record: dict) -> None:
        val = simpledialog.askstring("Add guest", "Name or email address:", parent=self.root)
        if not val:
            return
        val = val.strip()
        if "@" in val:
            record["invitees"].append({"name": val, "email": val})
        else:
            record["invitees"].append({"name": val, "email": contacts.resolve(val, self.account.get()) or ""})
        self._render_invitees(record)

    def _remove_guest(self, record: dict, inv: dict) -> None:
        record["invitees"] = [i for i in record["invitees"] if i is not inv]
        self._render_invitees(record)

    def _sync_time_state(self, record: dict) -> None:
        """Grey the time picker out on a Task — Tasks store a date, never a time."""
        try:
            record["time_cb"].config(
                state="readonly" if record["type"].get() == "event" else "disabled")
        except (tk.TclError, KeyError):
            pass
        self._refresh_count()

    @staticmethod
    def _row_problem(record: dict) -> str:
        """Why this row can't be created as configured, or '' if it's fine.

        A dateless Event is the one combination Calendar still cannot accept —
        `calendar_create_event` needs a `start`, so the router would be left
        inventing a date (and emailing it to real guests) or stopping to ask.
        Since events are now the default, this is mostly a prompt to supply the
        date that turns a task into something people actually get invited to.
        """
        if record["type"].get() == "event" and not record["date"].get().strip():
            return "an event with no date"
        return ""

    def _refresh_count(self) -> None:
        if not hasattr(self, "count_lbl"):
            return
        sel = [r for r in self.rows if r["include"].get()]
        ev = sum(1 for r in sel if r["type"].get() == "event")
        tk_ = len(sel) - ev

        bad = [r for r in sel if self._row_problem(r)]
        for r in self.rows:
            try:  # flag the offending field itself, not just the footer
                r["date_entry"].config(
                    foreground=WARN if (r["include"].get() and self._row_problem(r)) else "")
            except tk.TclError:
                pass

        emailing = bool(self.email_on_create.get())
        if bad:
            noun = "is an event with no date" if len(bad) == 1 else "are events with no date"
            self.count_lbl.config(
                text=f"⚠ {len(bad)} of {len(sel)} selected {noun} — add a date, or switch to Task",
                foreground=WARN)
        else:
            self.count_lbl.config(
                text=f"{len(sel)} of {len(self.rows)} selected — {ev} events, {tk_} tasks",
                foreground=MUTED)

        if not hasattr(self, "create_btn"):
            return
        if bad:
            label, state = "Create selected →", "disabled"
        elif sel:
            label = f"Create {len(sel)} + email →" if emailing else f"Create {len(sel)} →"
            state = "normal"
        elif emailing:
            # nothing to create, but the transcript is still worth banking
            label, state = "Email transcript only →", "normal"
        else:
            label, state = "Nothing selected", "disabled"
        self.create_btn.config(text=label, state=state)

    def _gather_items(self) -> list[dict]:
        items = []
        for r in self.rows:
            if not r["include"].get():
                continue
            action = r["action"].get().strip()
            if not action:
                continue
            emails = [i["email"] for i in r["invitees"] if i["email"]]
            unknown = [i["name"] for i in r["invitees"] if not i["email"]]
            typ = r["type"].get()
            notes = ""
            if typ == "task":
                # Tasks carry no guest list at all, so the names have to survive
                # somewhere or the person is silently lost. `notes` is that place —
                # folding them into the title produced live tasks reading
                # "…4 business (w/ jaded423@gmail.com)", because a typed address
                # IS its own display name.
                named = [i["name"] for i in r["invitees"]]
                if named:
                    notes = "With: " + ", ".join(named)
                emails = []
            elif unknown:  # event, but no address to invite → keep the name visible
                action = f"{action} (w/ {', '.join(unknown)})"
            items.append({
                "action": action,
                "date": _join_when(r["date"].get(), r["time"].get()),
                "type": typ,
                "invitees": emails,
                "notes": notes,
            })
        return items

    # ------------------------------------------------------------ audit email
    def _ledger(self) -> list[dict]:
        """Every row as it stands — including the ones you unchecked.

        The email is the audit artifact, so it records what was *skipped* too;
        that is the half you cannot reconstruct later from Calendar alone.
        """
        return [
            {
                "owner": r["owner"],
                "action": (r["action"].get().strip()
                           + ("  [2nd pass]" if r["flagged"] else "")
                           + ("" if r["include"].get() else "  [SKIPPED]")),
                "date": _join_when(r["date"].get(), r["time"].get()),
                "type": r["type"].get(),
            }
            for r in self.rows
        ]

    def _email_payload(self) -> tuple[str, str, str]:
        """(subject, body, transcript_path) for either email path."""
        when = self.meeting_date.get().strip() or date.today().isoformat()
        subject = f"Meeting transcript — {getattr(self, '_run_name', 'meeting')} ({when})"
        body = brain.format_coverage(self.coverage, self._ledger())
        return subject, body, (getattr(self, "_meta", {}) or {}).get("txt_path", "")

    def _email_target(self) -> str | None:
        to = self.email_to.get().strip()
        if not to or "@" not in to:
            messagebox.showwarning("No address", "Enter an email address to send the transcript to.")
            return None
        return to

    def _create(self) -> None:
        """The single send path: create the selected items, then email once.

        With nothing selected but the email box ticked, this degrades to
        transcript-only — the report still goes out, it just reports zero items.
        """
        blocked = [r for r in self.rows if r["include"].get() and self._row_problem(r)]
        if blocked:
            messagebox.showwarning(
                "Fix these first",
                f"{len(blocked)} selected item(s) are events with no date. Google Calendar "
                "needs a date to create an event, so add one — or switch the item to Task.",
            )
            return

        items = self._gather_items()
        email_to = ""
        if self.email_on_create.get():
            email_to = self._email_target() or ""
            if not email_to:
                return
        if not items and not email_to:
            messagebox.showwarning("Nothing to do", "Check an item to create, or tick the email box.")
            return

        subject, body, path = self._email_payload()
        if email_to and not path:
            if not items:
                messagebox.showerror(
                    "No transcript file",
                    "This run has no transcript file on disk to attach "
                    "(pasted text is not written out).",
                )
                return
            messagebox.showwarning(
                "Nothing to attach",
                "This run has no transcript file on disk, so the audit email will be skipped.",
            )
            email_to = ""

        n = len(items)
        if n:
            extra = f"\n\nIt will also email the transcript to {email_to}." if email_to else ""
            prompt = (f"This will create {n} item(s) in your '{self.account.get()}' account "
                      f"and email invites to any guests.{extra}\n\nProceed?")
            title = "Create in Calendar / Tasks?"
        else:
            prompt = (f"Nothing is selected, so nothing will be created.\n\n"
                      f"Email the transcript + report to {email_to}?")
            title = "Email the transcript?"
        if not messagebox.askyesno(title, prompt):
            return

        self._emailing = bool(email_to)
        if not n:  # email-only — no Calendar/Tasks write at all
            self.mail_status.config(text=f"sending to {email_to}…", foreground=MUTED)
            EmailWorker(email_to, subject, body, path, self.account.get(), self.queue).start()
            return

        self.create_worker = CreateWorker(
            items, self.account.get(), self.queue,
            email_to=email_to, transcript_path=path,
            email_subject=subject, coverage=self.coverage, ledger=self._ledger(),
        )
        self._show_creating(n)
        self.create_worker.start()

    def _show_creating(self, n: int) -> None:
        self._clear_body()
        ttk.Label(self.body, text=f"Creating {n} item(s)…",
                  font=("", 13, "bold")).pack(anchor="w", pady=(30, 8))
        bar = ttk.Progressbar(self.body, mode="indeterminate", length=440)
        bar.pack(anchor="w")
        bar.start(12)
        ttk.Label(self.body, text="Writing to Calendar / Tasks and sending invites…",
                  foreground=MUTED).pack(anchor="w", pady=(10, 0))

    def _show_result(self, summary: str, seconds: float) -> None:
        self._clear_body()
        ttk.Label(self.body, text="✓ Done", font=("", 15, "bold"),
                  foreground=OK).pack(anchor="w", pady=(20, 6))
        ttk.Label(self.body, text=f"Created in {_fmt(seconds)}.",
                  foreground=MUTED).pack(anchor="w", pady=(0, 10))
        box = tk.Text(self.body, height=14, wrap="word")
        box.pack(fill="both", expand=True)
        box.insert("1.0", summary or "(no summary returned)")
        box.config(state="disabled")
        # the audit email is sent after creation, so its outcome lands here
        self.result_mail = ttk.Label(
            self.body,
            text="sending the transcript email…" if getattr(self, "_emailing", False) else "",
            foreground=MUTED)
        self.result_mail.pack(anchor="w", pady=(8, 0))
        ttk.Button(self.body, text="New meeting", command=self.show_setup).pack(anchor="w", pady=12)

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export transcript", defaultextension=".txt",
            initialfile="transcript.txt", filetypes=[("Text", "*.txt")],
        )
        if path:
            Path(path).write_text(self.transcript, encoding="utf-8")

    # ---------------------------------------------------------------- polling
    def _poll(self) -> None:
        try:
            while True:
                msg = self.queue.get_nowait()
                self._handle(msg)
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def _handle(self, msg: tuple) -> None:
        tag = msg[0]
        if tag == "phase":
            phase = msg[1]
            if phase == "transcribing":
                self.prog_status.config(text="Transcribing…")
            elif phase == "thinking":
                self._phase_label = "thinking"
                self._update_step("Analyzing")
                self.prog_status.config(text="Reading the transcript for action items…")
                self.prog_nums.config(text="")
                self._set_indeterminate()
                self.prog_eta.config(text="")
            elif phase == "auditing":
                self._phase_label = "auditing"
                self._update_step("Double-checking")
                self.prog_status.config(text="Double-checking for anything the first pass missed…")
                self.prog_nums.config(text="")
                self._set_indeterminate()
                self.prog_eta.config(text="")
        elif tag == "progress":
            phase, frac = msg[1], msg[2]
            now = time.monotonic()
            if getattr(self, "_phase_label", None) != phase:
                self._phase_label = phase          # phase changed → restart ETA clock
                self._phase_t0 = now
            elapsed = now - getattr(self, "_phase_t0", now)
            self._update_step(phase)
            self.prog_status.config(text=f"{phase}…")
            if frac and frac > 0:
                self._set_determinate()
                self.pbar.config(value=frac * 100)
                eta = (elapsed / frac - elapsed) if frac > 0.02 else None
                self.prog_nums.config(text=f"{frac * 100:.0f}%")
                self.prog_eta.config(text=f"elapsed {_fmt(elapsed)} · ETA {_fmt(eta)}")
            else:
                self._set_indeterminate()
                self.prog_nums.config(text="")
                self.prog_eta.config(text=f"elapsed {_fmt(elapsed)}")
        elif tag == "transcribed":
            self._pending_meta = msg[1]
        elif tag == "proposed":
            coverage = msg[3] if len(msg) > 3 else None
            n_missed = len((coverage or {}).get("missed") or [])
            note = f" (+{n_missed} flagged by the 2nd pass)" if n_missed else ""
            _notify("Meeting Assistant",
                    f"Transcript ready — {len(msg[1])} items to review{note}.")
            self.show_review(msg[1], msg[2], getattr(self, "_pending_meta", {}), coverage)
        elif tag == "cancelled":
            self.show_setup()
        elif tag == "error":
            log.error("error: %s", msg[1])
            messagebox.showerror("Something went wrong", msg[1])
            self.show_setup()
        elif tag == "auth_error":
            log.error("auth: %s", msg[1])
            self._prompt_sign_in(msg[1], installed=bool(msg[2]) if len(msg) > 2 else True)
            self.show_setup()
        elif tag == "created":
            _notify("Meeting Assistant", "Items created in Calendar / Tasks.")
            self._show_result(msg[1], msg[2])
        elif tag == "create_error":
            log.error("create error: %s", msg[1])
            messagebox.showerror("Couldn't create items", msg[1])
            self.show_review_from_error()
        elif tag == "emailed":
            log.info("transcript emailed to %s", msg[1])
            self._mail_note(f"✓ transcript emailed to {msg[1]}", OK)
        elif tag == "email_error":
            # never fatal: the items are already created / still on screen
            log.error("email error: %s", msg[1])
            self._mail_note(f"⚠ transcript email failed — {msg[1]}", WARN)

    def _mail_note(self, text: str, color: str) -> None:
        """Report the email outcome wherever the user currently is."""
        for attr in ("mail_status", "result_mail"):
            widget = getattr(self, attr, None)
            try:
                if widget is not None and widget.winfo_exists():
                    widget.config(text=text, foreground=color)
                    return
            except tk.TclError:
                continue

    def _prompt_sign_in(self, detail: str, *, installed: bool = True) -> None:
        """Turn an expired sign-in into a one-click fix instead of an error.

        The whole app runs on the user's Claude subscription, so this fires on a
        predictable schedule for the life of the install — it has to read as a
        normal chore, not a crash.
        """
        path = brain.ensure_auth_command()
        if not installed:
            messagebox.showerror(
                "Claude Code isn't installed",
                "The Meeting Assistant needs Claude Code to read your transcripts.\n\n"
                "Install it in Terminal with:\n\n"
                "    npm install -g @anthropic-ai/claude-code\n\n"
                "Then sign in by double-clicking:\n\n"
                f"    {path}",
            )
            return
        if messagebox.askyesno(
            "Sign in to Claude",
            f"{detail}\n\n"
            "The Meeting Assistant uses your Claude subscription to read meetings, "
            "and that sign-in has to be renewed now and then.\n\n"
            "Open the sign-in window now?\n\n"
            "(You can also double-click this file any time:\n"
            f"{path})",
        ):
            try:
                subprocess.run(["open", path], check=False, timeout=15)
            except (OSError, subprocess.SubprocessError) as exc:
                log.error("could not open auth.command: %s", exc)
                messagebox.showerror(
                    "Couldn't open the sign-in window",
                    f"Open a Terminal and run:\n\n    claude auth login\n\n"
                    f"Or double-click:\n{path}",
                )

    def show_review_from_error(self) -> None:
        # creation failed after the review screen was torn down; go back to setup
        # rather than lose state silently. (Re-proposing is cheap.)
        self.show_setup()


def main() -> int:
    setup_logging()
    # Before anything probes for `claude` / ffprobe: a Finder-launched app gets
    # launchd's minimal PATH, not the shell's. Must run ahead of the auth check.
    log.info("PATH repaired -> %s", trans_runner.ensure_path())
    try:
        root = tk.Tk()
        try:
            root.tk.call("tk", "scaling", 1.4)
        except tk.TclError:
            pass
        App(root)
        root.mainloop()
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("fatal")
        try:
            messagebox.showerror("Meeting Assistant", f"Failed to start:\n{exc}\n\nSee {_LOG_DIR}")
        except tk.TclError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
