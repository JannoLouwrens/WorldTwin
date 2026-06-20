@AGENTS.md

# CLAUDE.md — Claude Code delta for WorldTwin

The shared, tool-agnostic brief is imported above from `AGENTS.md` (read it —
the four-point coding discipline, architecture, and safety rules all live there).
This file holds only the Claude-Code-specific bits.

## Use the skills — don't hand-roll ops

Operational procedures are packaged as skills in `.claude/skills/`. Prefer them
over improvising `scp`/`ssh`/`docker` commands:

| Task | Skill |
|---|---|
| Ship frontend changes to the live globe | `/deploy-frontend` |
| Restart / rebuild / force-fetch the aggregator | `/restart-aggregator` |
| Add a backend data source | `/add-plugin` |
| Add a frontend layer, mapmode, or mode | `/add-frontend-layer` |
| Disk full / WAL bloat / OOM-restart loop | `/disk-maintenance` |
| SSH in / inspect the live container stack | `/server-ssh-recipes` |

`deploy-frontend`, `restart-aggregator`, and `disk-maintenance` are **manual-only**
(`disable-model-invocation: true`) — they touch the live server, so invoke them
deliberately; I won't auto-run them.

## Sensitive / machine-specific facts

The server IP, SSH key path, and the resolved live deploy path are **not** in the
committed files (this repo is shared/private-but-shared). They live in:

- `CLAUDE.local.md` (git-ignored) — read it at the start of any server task.
- `.claude/skills/server-ssh-recipes/SKILL.md` — the SSH/topology reference.

Never write the server IP or SSH key path into `CLAUDE.md`, `AGENTS.md`, or any
committed file.

## Verifying frontend changes

Use the **chrome-devtools** MCP tools to load the live or local globe, take a
screenshot, and confirm the console has **0 JS errors** before calling a
frontend change done. "It should work" is not done; a clean console + visible
render is.
