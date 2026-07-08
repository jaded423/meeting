# meeting

> **Stack:** Tier-2 leaf. Parent: [mcp](~/projects/mcp/CLAUDE.md). Router: [global](~/.claude). Tier convention: [wiki-rollout-plan](~/.claude/docs/wiki-rollout-plan.md).

## Purpose

Transcription MCP — packages the `trans` stack (audio/URL/file → transcript) as Claude-usable tools; Cody's Claude handles extraction → Google Calendar/Tasks routing.

## Status

Scaffolded 2026-07-08 via `/newdir` (T0). **Dir born, MCP not built yet.** Built later by the `mcp` session from here. Blocked on `trans` landing FILE input + code-review (this MCP wraps the `trans` stack — see its TODO).

**Design doc (the what/why/how, engine bench, routing, human-in-loop):** [`~/projects/trans/docs/meeting-to-tasks-pipeline.md`](~/projects/trans/docs/meeting-to-tasks-pipeline.md). Delivery = 2 MCPs on Cody's Claude Desktop (`meeting` transcribes + `gsuite` routes to Calendar/Tasks); Cody's Claude = the extraction brain. Peer of `gsuite`/`leadscout` under the `mcp` hub; uses `trans`, not org-coupled to it.

## Layout

- `docs/` — typed-frontmatter notes (Tier-2 = notes only, no `wiki/`). Start at [docs/index.md](docs/index.md).
- `docs/changelog.md` — append-only history (`/log` writes here).
- `TODO.md` — open tasks + the session handoff (keep priority-ordered; first open item = what's next).

## Conventions

Keep THIS file lean + current-operational; cold content (history, design, build logs) → a typed `docs/*.md` this file points at. Memory homes + the one-home rule: [memory-architecture](~/.claude/docs/memory-architecture.md). This project's routing-map line lives in the global [CLAUDE.md](~/.claude/CLAUDE.md) "Active Projects" under **AI / Claude tooling**.
