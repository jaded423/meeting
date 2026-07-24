"""Background workers for the GUI — keep the heavy work off the Tk main thread.

Same pattern as photoEditor's ``ProcessorThread``: a ``threading.Thread`` runs the
slow work (transcribe → propose, or create), pushes tagged tuples onto a
``queue.Queue``, and the App drains that queue from a ``root.after`` poll so Tk is
only ever touched on the main thread. A ``threading.Event`` gives cooperative Cancel.

Queue messages (first element is the tag):
    ("phase", "transcribing" | "thinking")
    ("progress", phase_label: str, fraction: float | None)
    ("transcribed", {"words": int, "seconds": float, "engine": str})
    ("proposed", items: list[dict], transcript: str)
    ("cancelled",)
    ("error", message: str)
    ("created", summary: str, seconds: float)
    ("create_error", message: str)
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from .. import brain, contacts, transcribe


class TranscribeWorker(threading.Thread):
    """Transcribe the input, then ask the brain for a structured proposal."""

    def __init__(self, params: dict[str, Any], out_queue: "queue.Queue[tuple]"):
        super().__init__(daemon=True)
        self.p = params
        self.q = out_queue
        self.stop_event = threading.Event()

    def cancel(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        try:
            self.q.put(("phase", "transcribing"))

            def on_progress(phase: str, frac: float | None) -> None:
                self.q.put(("progress", phase, frac))

            result = transcribe.transcribe(
                self.p["input"],
                name=self.p["name"],
                out_dir=Path(self.p["out_dir"]),
                model=self.p["model"],
                diarize=self.p["diarize"],
                on_progress=on_progress,
                stop_event=self.stop_event,
            )

            text = result.get("text", "")
            self.q.put(("transcribed", {
                "words": len(text.split()),
                "seconds": result.get("seconds", 0.0),
                "engine": result.get("engine", ""),
            }))

            if self.stop_event.is_set():
                self.q.put(("cancelled",))
                return
            if not text.strip():
                self.q.put(("error", "The transcript came back empty — nothing to propose."))
                return

            self.q.put(("phase", "thinking"))
            account = self.p["account"]
            roster = list(contacts.people(account).keys())
            me = contacts.me(account).get("name") or "the user"
            items, res = brain.propose_structured(
                text,
                diarized=self.p["diarize"],
                me_name=me,
                roster_names=roster,
                anchor_date=self.p.get("meeting_date") or None,
            )
            if not res.ok and not items:
                self.q.put(("error", res.error or "The brain (claude -p) failed — see logs."))
                return
            if not items:
                self.q.put(("error", "The brain returned no action items it could parse."))
                return
            self.q.put(("proposed", items, text))

        except transcribe.TranscribeCancelled:
            self.q.put(("cancelled",))
        except transcribe.TranscribeError as exc:
            self.q.put(("error", str(exc)))
        except Exception as exc:  # noqa: BLE001 — surface anything to the UI + log
            self.q.put(("error", f"Unexpected error: {exc}"))


class CreateWorker(threading.Thread):
    """Create the approved items in Calendar / Tasks via the gsuite brain call."""

    def __init__(self, items: list[dict], account: str, out_queue: "queue.Queue[tuple]"):
        super().__init__(daemon=True)
        self.items = items
        self.account = account
        self.q = out_queue

    def run(self) -> None:
        try:
            res = brain.create_items(self.items, account=self.account)
            if res.ok:
                self.q.put(("created", res.output, res.seconds))
            else:
                self.q.put(("create_error", res.error or "claude -p failed while creating items."))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("create_error", f"Unexpected error: {exc}"))
