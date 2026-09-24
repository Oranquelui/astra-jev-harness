---
name: claude-jev-coding
description: "Select bounded repository context with Jev file-relevance judgments before implementing a coding task (feature, fix, refactor, tests) in the current Claude Code session. Use when the user asks for Jev context selection or claude-jev-coding in a Git checkout."
---

# Claude Code + Jev

You (the current Claude Code session) implement, review and test the change with your normal tools. Jev only judges which repository files are relevant. Do not start Codex, Astra or another coding agent for generation. This Skill does not change your model or effort.

## Entrypoint and credentials

Run `python3 "<base directory of this Skill>/scripts/context.py" <command> ...` using the absolute base directory shown when the Skill loads. Quote it; it may contain spaces. The wrapper resolves its symlink to `Claude Code/context.py` in the linked Harness checkout. `doctor` reports the checkout and whether a key is available, without calling a provider or printing the key.

An existing `TYPESAFE_API_KEY` takes precedence. On macOS the helper can read login Keychain service `astra-jev-harness`, account `TYPESAFE_API_KEY`, into its own process only. Never print keys, pass them as arguments, search `.env` files, or forward them. A missing key blocks `select` with Jev, not local planning. A Keychain timeout does not prove the key is absent.

## Workflow

1. Confirm the task and checkout. Read its CLAUDE.md/AGENTS.md, check branch, HEAD and status, and preserve existing changes.
2. Before reading implementation file bodies, write a focused task file outside the target and run `plan --repo <absolute-root> --task-file <file> --out <new-dir-outside-target>`. Read `PLAN.md` only (not `plan.json`). Untracked files need repeated `--include-file`; pin known task-critical files with `--focus-file`. For large repositories, scoping, or planning failures, read `references/workflow.md`.
3. Tell the user the planned Jev request count, then run `select --plan <plan-dir> --out <new-selection-dir> --max-calls <n> --mode auto`. `auto` keeps all candidates and skips Jev under 12,000 source bytes. Use `--mode jev` only when a real Jev evaluation is requested, and `--mode local` for a no-Jev baseline. The cap defaults to 4 (maximum 24). The helper makes no automatic retries, and a failed attempt may still be billed.
4. Read `REPORT.md` and only the metadata you need from `selection.json`: `decisions`, `unjudged_paths` and `metrics`. Do not dump `context.json`. Read bodies with `read --selection <dir> --path <relative-path> --start-line <n> --end-line <n>` (default 80 lines, maximum 200 lines or 24 KB). Uncertain, unjudged and dependency files are retained on purpose. A relevance score is not a security check.
5. Run `check --selection <dir>` before editing. Then implement and test directly in this session within the user's scope. The plan and selection grant no permission to edit, commit, push or take external actions.
6. If the source changes and you need more context, make a fresh plan. On failure, inspect the saved attempted and completed calls before any rerun.

Report actual Jev calls and usage from `selection.json`, separately from this session's usage. A zero-call selection is not Jev usage. Report implementation and test results independently of selection. The helper cannot measure Claude Code tokens or cost, and a smaller context is not a proven saving.

The helper rejects plans and selections from the Codex Desktop or CLI surfaces. It has no `run`, `verify` or `apply` commands. Selection artifacts contain source text. Keep them outside the target repository and out of Git.

For offline policy comparison (`compare`), evidence packets, caches and scope limits, read `references/workflow.md`.
