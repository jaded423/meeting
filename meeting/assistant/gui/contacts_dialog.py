"""In-app roster editor — add / edit / remove the people who can be invited.

Opened from the setup screen ("Manage guests…"). Edits the currently-selected
account's ``people`` map and persists straight to
``~/.config/meeting-assistant/contacts.json`` via :mod:`meeting.assistant.contacts`,
so no hand-editing of JSON is needed (matters for Cody's install too).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import contacts


class _PersonForm(tk.Toplevel):
    """Modal name + email entry. Sets self.result to (name, email) or None."""

    def __init__(self, parent, title: str, name: str = "", email: str = ""):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: tuple[str, str] | None = None
        self.transient(parent)

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Name").grid(row=0, column=0, sticky="w", pady=4)
        self.name_var = tk.StringVar(value=name)
        ttk.Entry(frm, textvariable=self.name_var, width=30).grid(row=0, column=1, pady=4, padx=(8, 0))
        ttk.Label(frm, text="Email").grid(row=1, column=0, sticky="w", pady=4)
        self.email_var = tk.StringVar(value=email)
        ttk.Entry(frm, textvariable=self.email_var, width=30).grid(row=1, column=1, pady=4, padx=(8, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="Save", command=self._save).pack(side="right")

        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Enter a name.", parent=self)
            return
        self.result = (name, self.email_var.get().strip())
        self.destroy()


class ContactsManager(tk.Toplevel):
    def __init__(self, parent, account: str):
        super().__init__(parent)
        self.parent = parent
        self.account = account
        self.title(f"Guests — {account}")
        self.minsize(420, 320)
        self.transient(parent)

        self.data = contacts.load()
        block = self.data.setdefault(account, {"me": {"name": "", "email": ""}, "people": {}})
        self.people: dict[str, str] = block.setdefault("people", {})

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"People who can be invited on '{account}' items:").pack(anchor="w", pady=(0, 8))

        cols = ("name", "email")
        self.tree = ttk.Treeview(frm, columns=cols, show="headings", height=10)
        self.tree.heading("name", text="Name")
        self.tree.heading("email", text="Email")
        self.tree.column("name", width=170)
        self.tree.column("email", width=230)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self._edit())

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Add…", command=self._add).pack(side="left")
        ttk.Button(btns, text="Edit…", command=self._edit).pack(side="left", padx=6)
        ttk.Button(btns, text="Remove", command=self._remove).pack(side="left")
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")

        self._reload()
        self.grab_set()

    def _reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for name in sorted(self.people):
            email = self.people[name]
            self.tree.insert("", "end", values=(name, email or "— no email —"))

    def _selected_name(self) -> str | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0], "values")[0]

    def _save(self) -> None:
        contacts.save(self.data)

    def _add(self) -> None:
        form = _PersonForm(self, "Add guest")
        self.wait_window(form)
        if form.result:
            name, email = form.result
            self.people[name] = email
            self._save()
            self._reload()

    def _edit(self) -> None:
        name = self._selected_name()
        if not name:
            return
        form = _PersonForm(self, "Edit guest", name=name, email=self.people.get(name, ""))
        self.wait_window(form)
        if form.result:
            new_name, email = form.result
            if new_name != name:
                self.people.pop(name, None)
            self.people[new_name] = email
            self._save()
            self._reload()

    def _remove(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if messagebox.askyesno("Remove guest", f"Remove {name}?", parent=self):
            self.people.pop(name, None)
            self._save()
            self._reload()
