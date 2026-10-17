# Claude Code Agent Skill

[日本語](README-ja.md) · [Repository overview](../README.md)

[`claude-jev-coding`](skills/claude-jev-coding/SKILL.md) is a Claude Code Agent Skill. The current Claude Code session implements, reviews and tests the change with its own tools. Jev only judges file relevance. The installed wrapper runs `bin/astra-jev claude-code`, using the native core shared with Desktop. It never starts Codex, Astra or another coding agent.

Requires the compiled `bin/astra-jev` executable and Git; Python is not a runtime dependency. No extra Python packages are needed.

## v0.7.3 model update

New Jev requests use fixed **`jev-1.14.0`**, through the native runtime shared with Desktop and CLI. It does not follow model aliases or change your active Claude model. TypeSafe reports multilingual improvements; Harness coding-quality, speed and total-cost improvements have not been measured. Existing thresholds, input bounds, no-retry behavior, local continuation and request-only usage reporting remain. [Official model specifications](https://docs.typesafe.ai/models) · [Release details](../README.md#v073-pin-jev-114-across-the-native-workflows).

Update the checkout/resources and executable together, then create a fresh plan and new output directories. Plans do not pin a model: selecting anew from an old plan also uses the current runtime's 1.14. Saved 1.13 judgments keep their original model and freshness checks; checking them does not call or validate 1.14. Model-containing request keys keep caches separate without deleting old entries. To roll back, use the matching v0.7.2 executable/resources with a fresh plan and new outputs, preserving old results and failure records. Existing Skill symlinks read the updated files; only repoint your own installation's link if changing directories. [Saved-judgment and rollback details](skills/claude-jev-coding/references/workflow.md#model-updates-and-saved-judgments).

## Install and check

Run these commands from the root of the cloned harness repository.

```sh
bin/astra-jev install --target claude-code --check   # prints the action, writes nothing
bin/astra-jev install --target claude-code           # links ~/.claude/skills/claude-jev-coding
# Project scope: link into a project's own skills directory instead.
bin/astra-jev install --target claude-code --skills-dir "/absolute/project/.claude/skills"
```

The installer creates one symlink to this clone. Running it again reports `already-installed`. It refuses to replace any existing file, directory or symlink with the same name, including broken links. It does not read or copy Claude Code or TypeSafe credentials, and it does not change settings, models or permissions. Keep the clone in place. To uninstall, remove only that symlink. `bin/astra-jev install` without `--target` still installs the Codex Desktop Skill.

To check the installation: `~/.claude/skills/claude-jev-coding/scripts/context.sh doctor` prints `"surface": "claude-code"`, the linked checkout, and whether a key is available. It never prints the key and does not call a provider.

## Invocation

Claude Code can load the Skill automatically from its description. You can also invoke it explicitly:

```text
/claude-jev-coding Fix pagination without changing the public API in this checkout.
```

The Skill does not pre-approve tools, override the model or effort, fork context, or inject shell output. Claude Code's normal permission prompts still apply to each helper command.

## Commands

`plan`, `select` (`--mode auto|jev|local`, `--policy batch|per-file`, `--max-calls`, `--cache-dir`, `--evidence`), `check`, `read`, `compare` and `doctor` behave the same as in the [Codex Desktop helper](../Codex%20Desktop/README.md). The differences:

- New plans and selections record surface `claude-code`. The helper rejects Desktop or CLI plans and selections, and the Desktop and CLI helpers reject Claude Code artifacts.
- The no-Jev route is recorded as `local`. The counter is `child_generation_calls: 0`, not `astra_child_calls`.

## Local continuation

When the user chooses no Jev, required files exceed the planning budget, credentials are unavailable, or Jev fails, state the cause and “Jev selection unverified — continuing locally” once and continue authorized work in the current session. Keep the choice for the task and in-scope follow-ups without asking again. An explicit requirement that Jev itself must succeed remains incomplete.

With a fresh, sufficient Claude plan, the installed `scripts/context.sh` supports `select --mode local`, `check` and `read` directly. It does not add Desktop's `--require-jev` flag. Local selection retains the plan's candidates as unjudged and cannot restore `scoped_out` files; `present` still requires Jev judgments. When no sufficient plan exists, use bounded native reads for the actual required files, preserving freshness, secrets, existing changes and the user's scope. Keep failed receipts, do not retry automatically, and do not drop dependencies or repeatedly increase caps to obtain a passing plan. [Commands and guardrails](skills/claude-jev-coding/references/workflow.md#local-continuation).

Routine replies focus on changes, verification and actionable blockers. Accounting is available only on request from saved records; do not add provider calls or benchmarks for reporting.

## Credentials and limits

The helper uses your own `TYPESAFE_API_KEY` from the environment, or on macOS the login Keychain item with service `astra-jev-harness` and account `TYPESAFE_API_KEY`. That key belongs to its process only. Jev usage is recorded in `selection.json`, separately from Claude Code conversation usage, which the helper cannot measure.

There is no conversation compaction, no hooks and no MCP server. No Claude Code token or cost reduction has been measured. The published benchmarks cover the Codex CLI workflow only.

## Verification

On 2026-09-24, Claude Code 2.1.281 discovered and invoked the project-installed Skill in an isolated synthetic Git repository. It used the linked helper for plan, local selection, freshness check and bounded reads, edited the fixture through its own tools, and passed all three acceptance tests while preserving their expectations. The saved selection records zero attempted/completed Jev calls and zero child generation calls. This verifies the native Skill workflow in local mode; live Jev behavior is covered by offline mocked-provider tests, not a Claude live-Jev benchmark. `claude plugin validate "Claude Code/skills"` and all 141 offline harness tests passed.
