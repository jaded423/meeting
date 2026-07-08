# meeting — TODO

> Session handoff lives here. Keep priority-ordered — first open item = what's next.
> Cross-project / no-single-home tasks go to `~/.claude/TODO.md`, not this file.

> **Design doc = [`~/projects/trans/docs/meeting-to-tasks-pipeline.md`](~/projects/trans/docs/meeting-to-tasks-pipeline.md).** Build from the `mcp` session, from this dir.

**Blocked on `trans`** — this MCP wraps the trans stack; needs trans FILE input + code-review to land first (see `~/projects/trans/TODO.md`).

- [ ] **Build the MCP** (from the `mcp` session) — package the `trans` stack as Claude tools. Minimum: `meeting.transcribe` (audio/URL/file → text). Cody's Claude does extraction; `gsuite` (`calendar_create_event` + `tasks_*`, both built) does routing. Add to `mcp` `install-all.sh` + register `mcp__meeting__*` in global CLAUDE.md.
- [ ] Confirm Cody Mac specs + Plaud-device-vs-file input (open Qs in design doc) before locking the capture adapter/engine.
