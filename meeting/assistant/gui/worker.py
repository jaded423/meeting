"""Background workers for the GUI — keep the heavy work off the Tk main thread.

Same pattern as photoEditor's ``ProcessorThread``: a ``threading.Thread`` runs the
slow work (transcribe → propose, or create), pushes tagged tuples onto a
``queue.Queue``, and the App drains that queue from a ``root.after`` poll so Tk is
only ever touched on the main thread. A ``threading.Event`` gives cooperative Cancel.

Queue messages (first element is the tag):
    ("phase", "transcribing" | "thinking" | "auditing")
    ("progress", phase_label: str, fraction: float | None)
    ("transcribed", {"words": int, "seconds": float, "engine": str, "txt_path": str})
    ("proposed", items: list[dict], transcript: str, coverage: dict)
    ("cancelled",)
    ("error", message: str)
    ("auth_error", detail: str, cli_installed: bool)
    ("created", summary: str, seconds: float)
    ("create_error", message: str)
    ("emailed", to: str)
    ("email_error", message: str)
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
            # Check the Claude sign-in FIRST. It costs a second, and the
            # alternative is transcribing for 20 minutes before failing.
            auth = brain.auth_status()
            if not auth.ok:
                self.q.put(("auth_error", auth.detail, auth.installed))
                return

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
                # the .txt on disk — what the audit email attaches (by path, never
                # through a model's context)
                "txt_path": (result.get("files") or {}).get("txt", ""),
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
            anchor = self.p.get("meeting_date") or None
            diarized = self.p["diarize"]

            items, res = brain.propose_structured(
                text,
                diarized=diarized,
                me_name=me,
                roster_names=roster,
                anchor_date=anchor,
            )
            if not res.ok and not items:
                # backstop: the sign-in can lapse between the pre-flight and here
                if brain.looks_like_auth_failure(res):
                    self.q.put(("auth_error", "Your Claude sign-in expired mid-run.", True))
                else:
                    self.q.put(("error", res.error or "The brain (claude -p) failed — see logs."))
                return
            if not items:
                self.q.put(("error", "The brain returned no action items it could parse."))
                return

            coverage: dict[str, Any] = {"topics": [], "missed": []}
            if self.p.get("audit") and not self.stop_event.is_set():
                self.q.put(("phase", "auditing"))
                # A failed audit must never cost us the items the first pass DID find,
                # so this is best-effort: on error we fall through with an empty ledger
                # and the review panel simply shows no coverage section.
                try:
                    coverage, _ = brain.audit_coverage(
                        text, items,
                        diarized=diarized,
                        me_name=me,
                        roster_names=roster,
                        anchor_date=anchor,
                    )
                except Exception:  # noqa: BLE001
                    coverage = {"topics": [], "missed": []}

            if self.stop_event.is_set():
                self.q.put(("cancelled",))
                return
            self.q.put(("proposed", items, text, coverage))

        except transcribe.TranscribeCancelled:
            self.q.put(("cancelled",))
        except transcribe.TranscribeError as exc:
            self.q.put(("error", str(exc)))
        except Exception as exc:  # noqa: BLE001 — surface anything to the UI + log
            self.q.put(("error", f"Unexpected error: {exc}"))


class CreateWorker(threading.Thread):
    """Create the approved items in Calendar / Tasks via the gsuite brain call.

    When `email_to` is set, the audit email follows the creation — so the body can
    report what was actually created, not just what was proposed.
    """

    def __init__(self, items: list[dict], account: str, out_queue: "queue.Queue[tuple]",
                 *, email_to: str = "", transcript_path: str = "", email_subject: str = "",
                 coverage: dict | None = None, ledger: list[dict] | None = None):
        super().__init__(daemon=True)
        self.items = items
        self.account = account
        self.q = out_queue
        self.email_to = email_to
        self.transcript_path = transcript_path
        self.email_subject = email_subject
        # The body is rendered *after* creation, not before, so the CREATED
        # section can report what actually landed.
        self.coverage = coverage or {}
        self.ledger = ledger or []

    def run(self) -> None:
        try:
            results, res = brain.create_items(self.items, account=self.account)
            if res.ok:
                self.q.put(("created", brain.format_created(results), res.seconds))
            elif brain.looks_like_auth_failure(res):
                self.q.put(("auth_error", "Your Claude sign-in expired.", True))
                return
            else:
                self.q.put(("create_error", res.error or "claude -p failed while creating items."))
                return
        except Exception as exc:  # noqa: BLE001
            self.q.put(("create_error", f"Unexpected error: {exc}"))
            return

        if not self.email_to:
            return
        try:
            body = brain.format_coverage(
                self.coverage, self.ledger, created=brain.format_created(results)
            )
            mail = brain.email_transcript(
                self.email_to, self.email_subject, body, self.transcript_path,
                account=self.account,
            )
            self.q.put(("emailed", self.email_to) if mail.ok
                       else ("email_error", mail.error or "the transcript email failed to send."))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("email_error", f"Unexpected error: {exc}"))


class EmailWorker(threading.Thread):
    """Send the transcript + audit report on its own — no Calendar/Tasks writes.

    The path that matters for a meeting you did not attend: bank the raw source
    first, decide what to create afterwards.
    """

    def __init__(self, to: str, subject: str, body: str, transcript_path: str,
                 account: str, out_queue: "queue.Queue[tuple]"):
        super().__init__(daemon=True)
        self.to = to
        self.subject = subject
        self.body = body
        self.transcript_path = transcript_path
        self.account = account
        self.q = out_queue

    def run(self) -> None:
        try:
            res = brain.email_transcript(
                self.to, self.subject, self.body, self.transcript_path, account=self.account,
            )
            self.q.put(("emailed", self.to) if res.ok
                       else ("email_error", res.error or "the transcript email failed to send."))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("email_error", f"Unexpected error: {exc}"))
