# Storybloq initial setup — NoAmp Low Rider DI

## What happened this session

Storybloq had never been wired up for this project — no `.story/` anywhere in the tree, and no
MCP server registered in `~/.claude.json`. Both were set up:

1. **MCP registration.** The `claude` CLI binary doesn't exist on this machine (Claude Code runs
   as the VSCode extension only), so `storybloq setup --client all` couldn't auto-register the
   server — it explicitly skipped with "claude CLI not found in PATH". Registered manually by
   adding a `storybloq` entry directly to `~/.claude.json`'s top-level `mcpServers` (backed up the
   original file first as `.claude.json.bak-<timestamp>`), pointing at `/opt/homebrew/bin/storybloq
   --mcp`. Smoke-tested the server's JSON-RPC `initialize` handshake directly over stdin/stdout —
   confirmed v1.8.0 responds correctly. **MCP tools will only become dispatchable after Claude Code
   is restarted** (it loads MCP servers at startup only); until then, this project uses the CLI.

2. **Project init.** This is a mature project (Phase 0–9 shipped per `docs/build-plan.md`,
   currently mid-Phase-10 capture-validation) with unusually deep existing tracking in `CLAUDE.md`
   and `docs/phase10-gap-audit.md` — the gap audit was already a near-perfect issue backlog. Kept
   the Storybloq structure lean rather than duplicating that detail:

   - **10 phases** created 1:1 from `docs/build-plan.md`'s real phase list (scaffold →
     v1e-linear → v1e-nonlinear → v1e-integration → zener-spike → v1l-dsp → v2-dsp →
     revision-switch → ui → probes-ci → capture-validation). No phase-complete flag exists in this
     schema version (completion is ticket-derived, not a phase field), so phases 0–9 aren't marked
     "complete" anywhere in Storybloq itself — CLAUDE.md/build-plan.md remain the authoritative
     record of what shipped.
   - **6 issues** (ISS-001..006) filed directly from `docs/phase10-gap-audit.md`'s six open gaps
     (A–F), each `dedupeKey`'d as `phase10-gap-audit:<letter>` so a future retry/import doesn't
     duplicate them. Severities: ISS-001 (gap A, THD slope) = high (explicitly "Open — next" in
     the audit); ISS-002 (gap B), ISS-004 (gap D), ISS-006 (gap F) = medium; ISS-003 (gap C),
     ISS-005 (gap E) = low.
   - **1 ticket** (T-001) for gap A, the audit's explicit next priority, phase capture-validation,
     linked to ISS-001 via `relatedTickets`.
   - **Quality pipeline:** TEST stage only, command `cmake --build build -j8 && (cd build &&
     ctest)` — matches the project's own standing rule in `phase10-gap-audit.md` ("ALWAYS rebuild
     ALL targets before believing ctest" — a partial `--target` build produced a false "23/23
     green" in two separate real sessions and hid a bug for a week). No VERIFY (not a server) and
     no separate BUILD stage (the TEST command already does a full rebuild).
   - **CLAUDE.md/RULES.md:** left untouched. Both already exist and are extensive (CLAUDE.md alone
     runs ~2k tokens of dense carry-forward notes); regenerating would have been strictly worse
     than what's there.
   - **`.gitignore`:** appended `.story/snapshots/`, `.story/sessions/`, `.story/status.json`
     (repo already existed and was already a git repo, so no `git init` needed).
   - Took an initial `storybloq snapshot` as the baseline for future recaps.

## Gates answered (per setup-flow.md 1f)

- Surface: existing native macOS/cross-platform audio plugin (AU/VST3), not asked via the
  interview funnel — this went through the "1b. Existing Project — Analyze" path, not "1c. New
  Project — Interview", since `.git`/CMakeLists.txt/extensive docs were all present.
- Stack: CMake + JUCE 8 + chowdsp_wdf, C++17 — read directly from CMakeLists.txt and CLAUDE.md,
  not asked.
- Quality checks: user chose "Tests only" (Recommended) over "Full pipeline" (which would have
  added `ab_report.py`-style verification scripts as a required gate) or "Minimal".
- Design source: not asked (not applicable — this is a native fixed-topology plugin UI, not a
  web/mobile app with a design-system gate).
- Auth/data model/domain complexity/AI pattern: not applicable, all skipped per setup-flow.md's
  skip rules for a project of this shape.

## Also noted mid-session (not a Storybloq action, just an observation worth carrying forward)

The auto-loaded CLAUDE.md context at session start was one branch/session behind reality — it
referenced branch `phase10-v1e-drive-taper`, but `git log`/`git branch` show work has since moved
to `main` (that branch no longer exists) and two more commits landed (`cb0fe9b` V1E THD-onset fit +
DC bug fix, `960c92c` a CLAUDE.md correction of a wrong mid-session claim). `docs/phase10-gap-audit.md`
on disk is already the refreshed, authoritative version and is what ISS-001..006 above were filed
from — not the stale system-prompt snapshot. Next session's `/story` load should already reflect
this correctly via `storybloq_recap`/git log, since Storybloq reads from disk, not from the AI
client's context window.

## Next up

T-001 / ISS-001 (gap A: V1E THD-vs-frequency slope) is the recommended next work, exactly matching
what `docs/phase10-gap-audit.md` already called "Open — next" before Storybloq existed.
