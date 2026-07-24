"""Contacts / roster for invitee resolution.

The transcript names a person ("Erica"); a Google Calendar invite needs an email.
This module owns that name→email map, plus the identity of whoever is running the
app (so their OWN action items never get a self-invite).

One JSON config per install at ``~/.config/meeting-assistant/contacts.json``,
keyed by gsuite account (elevated / jaded / point4 / brown). Seeded on first run
with the Elevated team and their ``@elevatedtrading.com`` addresses. A name with
no email still shows as a chip in the review panel, flagged "no email"; at create
time that item falls back to naming the person in the title instead of inviting.

Manage the roster in-app (setup screen → "Manage guests…"), or edit this file by
hand. New people default to blank email until you give them one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "meeting-assistant"
CONFIG_PATH = CONFIG_DIR / "contacts.json"

# Seed: names only where we don't KNOW the address. Fill the blanks once and the
# app will invite them automatically thereafter. (joshua@ / jaded423@ / the spare
# brown@ account are known; everyone else is intentionally blank.)
_SEED: dict[str, Any] = {
    "elevated": {
        "me": {"name": "Joshua Brown", "email": "joshua@elevatedtrading.com"},
        "people": {
            "Cody Sandone": "cody@elevatedtrading.com",
            "Justin Sandone": "justin@elevatedtrading.com",
            "Joe Gibson": "joe@elevatedtrading.com",
            "Cynthia Castruita": "cynthia@elevatedtrading.com",
            "Erica Mechah": "erica@elevatedtrading.com",
        },
    },
    "jaded": {
        "me": {"name": "Joshua Brown", "email": "jaded423@gmail.com"},
        "people": {},
    },
    "point4": {
        "me": {"name": "Joshua Brown", "email": ""},
        "people": {"Cody Sandone": ""},
    },
    "brown": {
        "me": {"name": "Joshua Brown", "email": "brown.joshua.david@gmail.com"},
        "people": {},
    },
}


def load() -> dict[str, Any]:
    """Return the contacts config, creating the seed on first run."""
    if CONFIG_PATH.is_file():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # corrupt / unreadable → fall through to the seed
    save(_SEED)
    return json.loads(json.dumps(_SEED))  # deep copy


def save(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def accounts() -> list[str]:
    return list(load().keys()) or ["elevated"]


def _block(account: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data if data is not None else load()
    return data.get(account) or data.get("elevated") or {"me": {}, "people": {}}


def me(account: str, data: dict[str, Any] | None = None) -> dict[str, str]:
    return _block(account, data).get("me") or {"name": "", "email": ""}


def people(account: str, data: dict[str, Any] | None = None) -> dict[str, str]:
    return _block(account, data).get("people") or {}


def resolve(name: str, account: str, data: dict[str, Any] | None = None) -> str | None:
    """Best-effort email for a person named in the transcript.

    Exact (case-insensitive) full-name match first, then a first-name match.
    Returns None if unknown or the mapped email is blank.
    """
    if not name:
        return None
    roster = people(account, data)
    low = name.strip().lower()
    for full, email in roster.items():
        if full.strip().lower() == low and email:
            return email
    first = low.split()[0] if low.split() else low
    for full, email in roster.items():
        if full.strip().lower().split()[:1] == [first] and email:
            return email
    return None
