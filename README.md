# Astra + Jev: Codex Agent Skill and CLI Harness

[日本語](README-ja.md) · [Version 0.3.0](VERSION) · [Tagged releases](https://github.com/Oranquelui/astra-jev-harness/releases) · [Changelog](CHANGELOG.md)

This repository provides the **[`astra-jev-coding` Codex Agent Skill](desktop/skills/astra-jev-coding/SKILL.md) for Codex Desktop** and a separate harness for Codex CLI. Install the Skill to use Jev for context selection while the current Desktop conversation implements the task; the CLI workflow runs Codex separately.

Narrow large repositories locally, let **Jev judge the bounded candidates**, then let **Astra write the code**.

A local coding harness for Codex CLI and Codex Desktop. Give it a task such as “fix pagination without changing the public API”; it snapshots eligible files, locally narrows oversized repositories, asks Jev which candidates the coding model needs, preserves dependencies, and records what was kept and why.

**Experimental.** v0.3.0 improves selection coverage and makes context/cost accounting explicit. **End-to-end Astra token and total-cost savings from this upgrade are not established.** The historical 1.2% Astra-input reduction below predates this version. [Measurements and limits](docs/BENCHMARKS.md).

## What improved in v0.3.0?

| Area | v0.2.0 | v0.3.0 |
|---|---|---|
| Eligible files larger than 22 KB | Retained without a Jev judgment | Every range is judged within a request budget; uncertainty or missing coverage retains the whole file |
| Desktop handoff | Skill reads the full selected context | Skill selects before loading implementation bodies, then reads needed line ranges |
| Small Desktop tasks | `select` always uses Jev when there are judgeable files | Skill recommends `--mode auto`: below 12,000 source bytes, retain candidates with zero Jev calls; command default remains `jev` |
| Usage and cost | Provider token totals; no price estimate | Separate ordinary input, cache reads/writes and unknowns; optional exact-model price estimates |

These changes apply to the Codex Desktop Skill; complete-range selection and accounting also support CLI. Existing plans keep their replay behavior. Exact-request Jev response reuse already existed in v0.1.0 and is **not a new v0.3.0 saving**. [Upgrade details](docs/CONTEXT-BUDGETS.md) · [Changelog](CHANGELOG.md).

## Evidence-aware coding (experimental)

Select original evaluation excerpts with source hashes and line numbers, retain pinned failure/budget records, reuse identical Jev requests, and compare saved run usage. Both CLI and Desktop accept the resulting evidence packet. [Commands and limits](docs/EVIDENCE.md).

## Pick your workflow

| | Codex CLI | Codex Desktop app |
|---|---|---|
| Who writes code? | A separate Codex CLI process using Astra | The model in your current conversation; select Astra for the Astra workflow |
| What does Jev do? | Selects context before generation | Selects files for the current conversation to read |
| Workflow | `plan → run → verify → apply` | `plan → select → check → implement/test in the conversation` |
| Target writes | Explicit `apply` after verification | Your normal Desktop editing tools |
| Entrypoint | `python3 cli/main.py` | `python3 desktop/context.py` or the Skill |

Desktop does **not** spawn another Codex CLI to generate code. Neither workflow registers Jev as a model in Codex's Model menu.

## Start here

Requires Python **3.10+**, Git, your own TypeSafe API key, and Codex. No third-party Python runtime dependencies. Tested locally on macOS with Python 3.14 and Codex CLI 0.153.2; other platforms and Codex versions are not established by that measurement. CLI generation requires access to `gpt-6-astra` in your own Codex account and a working `codex sandbox` command. The included runtime flags are version-sensitive.

```sh
git clone https://github.com/Oranquelui/astra-jev-harness.git
cd astra-jev-harness
python3 -m unittest -v
```

Use **your own credentials**:

```sh
# Replace the placeholder locally, or supply it through your secret manager.
export TYPESAFE_API_KEY="YOUR_OWN_TYPESAFE_API_KEY"

# CLI generation only: log in to your own account if needed.
codex login
python3 cli/main.py doctor
```

No maintainer API key, Codex login, session cookie, or authentication file is included. Never commit a real key. `doctor` reports availability, not the value; it does not call an API. Existing environment values take precedence. On macOS, an already-configured login Keychain item with service `astra-jev-harness` and account `TYPESAFE_API_KEY` can be used instead. The installer does not create that item or share anyone else's account.

### Codex Desktop

```sh
python3 install.py --check
python3 install.py
```

This links only the Desktop Skill into `$CODEX_HOME/skills` (default `~/.codex/skills`). It refuses to overwrite a different existing Skill, changes no Codex model settings, and does not read or copy your login. Keep this clone in place. To uninstall, remove only the `astra-jev-coding` symlink created by the installer. If it is not visible yet, start a new Codex task.

Open the target repository in Codex Desktop and ask:

```text
$astra-jev-coding Fix this task with Astra + Jev in the current checkout.
```

The Skill uses your task and repository instructions, reviews the files to send, selects context, checks freshness, and continues implementation in that conversation. If the Desktop process cannot see your shell environment, use the helper from a terminal with the key configured or the optional Keychain lookup; `export` in a separate terminal does not change an already-running app's environment.

### CLI: an isolated example

Run these from the clone root. Plan and run directories must be outside the target repository and must not already exist.

```sh
DEMO_ROOT=$(mktemp -d)
python3 make_demo.py "$DEMO_ROOT/repo"
printf '%s\n' 'Fix page_items: page numbers start at 1. Clamp page and explicit size to at least 1; use DEFAULT_PAGE_SIZE only when size is None. Preserve the API and tests.' > "$DEMO_ROOT/task.txt"

# Local inspection only. Review PLAN.md before sending source to a provider.
python3 cli/main.py plan --repo "$DEMO_ROOT/repo" \
  --task-file "$DEMO_ROOT/task.txt" --out "$DEMO_ROOT/plan"

# Paid/provider usage: at most 24 Jev requests and 2 Astra generations.
python3 cli/main.py run --plan "$DEMO_ROOT/plan" \
  --out "$DEMO_ROOT/run" --mode jev \
  --verify-json '["python3", "-B", "-m", "unittest", "discover"]'

# Review REPORT.md, changes.diff, and verification output first.
python3 cli/main.py apply --run "$DEMO_ROOT/run"
```

`run` writes a candidate outside the target. `apply` accepts only verified, unchanged artifacts and leaves changes uncommitted. `verify --run ...` reruns verification without another model call. New files and existing test edits require explicit plan flags: `--allow-create path` and `--allow-test-edit path`. [CLI details](docs/CLI.md).

## What it does

Select before loading bodies into the conversation, then use `read --selection /absolute/selection --path src/main.py --start-line 1 --end-line 80` for needed ranges. `select --mode auto` skips Jev under 12,000 source bytes; `--mode local` explicitly bypasses it (default remains `jev`). Measurement separates cache reads/writes and supports supplied model-specific price estimates. [Behavior and limits](docs/CONTEXT-BUDGETS.md).

- **Bounded selection.** Complete eligible sources are split into bounded ranges and grouped with their questions into requests. Uncertain judgments preserve context. Resolvable Python/relative JavaScript dependencies, configuration, and repository instructions are retained.
- **Visible decisions.** Source-range probabilities, per-file retention reasons, incomplete judgments, and before/after source bytes are recorded. Relevance is not a security verdict.
- **Local policy comparison.** Replay saved judgments with no API call. Independently identified required-file labels can include paths in the plan or `scoped_out`, exposing local-scope misses separately from Jev-selection misses; without labels, recall is unknown.
- **Freshness checks.** Desktop checks the plan and selected content against repository HEAD, branch, status, file contents, and modes. A historical comparison does not authorize using stale context.
- **Scoped edits.** CLI verifies a candidate in Codex's read-only sandbox, checks its integrity, then applies permitted edits with collision checks and recovery records.
- **Explicit failures.** No automatic service retries. CLI checks the serialized worst-case Astra prompt against its 500,000-byte limit before any Jev call. Desktop records attempted and completed requests and refuses to reuse an output directory. Failed requests may still be billable.

```sh
python3 desktop/context.py plan --repo /absolute/repo \
  --task-file /absolute/task.txt --out /absolute/plan
python3 desktop/context.py select --plan /absolute/plan \
  --out /absolute/selection --max-calls 4 --mode auto
python3 desktop/context.py check --selection /absolute/selection
python3 desktop/context.py compare --selection /absolute/selection \
  --required-file src/main.py
```

The default `batch` policy retains an entire batch when any judgment is uncertain. The experimental `select --policy per-file` retains uncertain/unjudged files while omitting confidently irrelevant siblings. Dependencies and the global no-match fallback still apply. Compare before changing policy; fewer bytes alone do not establish correctness.

## Larger repositories

When eligible files exceed **2,000,000 bytes, 1,500 files, or the planned request budget**, `plan` first builds a deterministic, task-aware lexical shortlist **locally**, before any Jev request. Desktop's scoped plan is capped at 2,000,000 bytes. CLI uses a tighter 350,000-byte scoped cap to leave room under its separate 500,000-byte Astra prompt limit. Plans within all three bounds retain the full candidate set. Full file contents are retained within the shortlist; files are not silently truncated.

Use repeated `--focus-file` paths for eligible files you know the task needs. `--scope-max-calls` caps the **planned** Jev requests for the candidate scope (default 4, range 1–24); the later `select --max-calls` execution cap remains separate. Untracked files still require `--include-file`. A focus path cannot bypass eligibility or the 100 KB per-file limit.

```sh
python3 desktop/context.py plan --repo /absolute/repo \
  --task-file /absolute/task.txt --out /absolute/plan \
  --focus-file src/pagination.py --focus-file tests/test_pagination.py \
  --scope-max-calls 4
```

The same two planning flags are available in `cli/main.py plan`. Review `PLAN.md` before sending code: it reports the original eligible count/bytes, the scoped-out paths/bytes, and planned Jev calls. `plan.json` stores the totals under `scope` and omitted eligible file metadata under `scoped_out`. These files were **not judged by Jev**; they differ from protected/ineligible `excluded` files and Jev-rejected files. Instructions, key configuration, and resolvable dependencies remain in scope. The lexical stage does not translate: a Japanese-only task without an ASCII path or identifier may need `--focus-file`. If no task/file match is found **and no required path is supplied**, or mandatory files cannot fit, planning fails and asks for a more specific task or focus path. Required-file recall and Astra token effects remain unknown until independently measured. [Design and official TypeSafe references](docs/DESIGN.md).

## How much does it save?

### v0.2.0 → v0.3.0: the same synthetic input

One two-file fixture, the same task and content hashes, conservative `batch` policy, and `main.py` explicitly pinned. This is a selection check, not a completed coding benchmark.

| Measured selection metric | v0.2.0 | v0.3.0 |
|---|---:|---:|
| Fully judged files | 1 / 2 | 2 / 2 |
| Retained source bytes | 27,353 | 75 |
| Live Jev requests | 1 | 2 |
| Jev input tokens | 392 | 6,784 |
| Jev output tokens | 21 | 76 |
| Estimated Jev API cost | $0.000016464 | $0.000284928 |

The unrelated 27,278-byte file is now judged and omitted: **99.73% fewer retained source bytes in this deliberately simple example**. This is not a token-saving percentage. Judging the previously skipped content added an estimated **$0.000268464** in Jev cost. Whether Astra saves more than that remains unmeasured, including cache effects and subsequent rereads. Prices use actual reported Jev input at **$0.042 per million**, with free output, checked 2026-09-24; these are estimates, not invoices. [Official price](https://docs.typesafe.ai/models).

A separate 75-byte fixture using the new `auto` mode made **zero Jev calls**, avoiding selection overhead while retaining its source. Neither check measured complete Desktop conversation usage or Codex subscription limits. [Method, limitations and comparison formula](docs/BENCHMARKS.md#v030-upgrade-check--2026-09-24) · [Aggregate data](benchmarks/context-selection-v0.3.0.json).

### Historical Astra generation comparison — not the v0.3.0 effect

Historical controlled rerun: three small synthetic Python tasks, one trial per task and mode. Same Astra model and reasoning setting; 22 behavior checks passed in each arm.

| Metric, three tasks combined | Astra only | Astra + Jev | Observed change |
|---|---:|---:|---:|
| Candidate files sent to Astra | 28 | 4 | **85.7% fewer** |
| Harness-written prompt characters | 4,309 | 2,581 | **40.1% fewer** |
| Astra-reported input tokens | 42,714 | 42,199 | **1.2% fewer** |
| Astra-reported output tokens | 175 | 175 | Unchanged |
| Elapsed time | 18.51 s | 21.53 s | **16.3% longer** |
| Jev input tokens | — | 4,094 | Separate provider usage |

These are historical measurements, **not a benchmark of every feature in this release**. Dollar savings, Codex weekly-limit consumption, and end-to-end Desktop token savings were not measured. Do not add different providers' tokens together to infer price. The context-selection layer cannot remove Codex's shared instructions, tools, or existing conversation history. [Method, caveats, later selection results, and reproduction](docs/BENCHMARKS.md) · [Aggregate data](benchmarks/results-2026-09-22.json).

## How it works

```mermaid
flowchart LR
  T[Task + local Git snapshot] --> S[Local scope if repo exceeds bounds]
  S --> J[Jev: file relevance judgments]
  J --> P[Local policy + dependency retention]
  P --> C[CLI: Astra generation]
  C --> V[Isolated verification]
  V --> A[Explicit apply]
  P --> D[Desktop: context handoff]
  D --> F[Freshness check]
  F --> E[Current conversation edits and tests]
```

`shared/` owns TypeSafe transport, snapshots, selection, and credential lookup. `cli/` owns generation, candidate verification, and apply. `desktop/` owns the context handoff and Skill. Root scripts remain compatibility entrypoints. Jev answers Noul yes/no relevance questions; it does not generate code. Code enforces limits and paths.

## What leaves your machine

`plan`, `check`, `read`, and `compare` are local. When Jev is used, `select` sends the task, relative paths, and eligible source contents to TypeSafe; locally `scoped_out` file contents are not sent to Jev. CLI generation sends selected context and at most 512 scoped-out **file names** (plus the omitted-file count) to Codex using your own login, so Astra can request a fresh plan if context is missing. The harness removes `TYPESAFE_API_KEY`, `OPENAI_API_KEY`, and `CODEX_API_KEY` from the Astra child environment. It does not export or package your Codex login.

Plans, candidates, and run files contain source text. Store them outside the target repository and keep them out of Git. The source filter rejects known credential patterns and excluded file types; it is not a complete secret detector. Review `PLAN.md` before sending private code. [Security and credential handling](SECURITY.md).

## Current limits

- Tracked eligible UTF-8 files plus explicitly included untracked files: a scoped plan holds up to 2 MB total, 1,500 files, and 100 KB per file. Above 2 MB, 1,500 eligible files, or the planned request budget, local task-aware scoping applies; CLI's scoped byte cap is 350,000. Use reviewed `plan --include-file` paths for untracked files; no staging is required.
- New plans judge complete ranges of files over 22 KB; uncertain/unjudged ranges retain the whole file. Old plans replay their original policy. [Budgets and accounting](docs/CONTEXT-BUDGETS.md).
- Dependency discovery is partial. Conventional Python `src` roots, local TS aliases and `.mts` are supported; dynamic imports and arbitrary build configurations remain partial.
- CLI verification does not install dependencies; read-only verification may not support builds that write artifacts. Passing supplied tests is not proof of complete correctness.
- Desktop has no automatic model routing, conversation compaction, or total-session token meter. The current model remains the model you selected.
- Experimental thresholds (0.2/0.8) are not calibrated guarantees for your repository.

## Related projects

| Project | Main job | Relationship |
|---|---|---|
| [hermes-jev-skills](https://github.com/kerpopule/hermes-jev-skills) | Jev-based agent decisions including routing, retrieval, and skill selection | Informed our explicit judgment coverage and evaluation-first policy comparison |
| [jev-lint](https://github.com/mizchi/jev-lint) | Semantic lint questions over matched code | Informed the README's concrete examples, setup, measured results, and limitations; not bundled |
| This project | File-context selection for two Codex coding workflows | Generation/verification/apply in CLI; native conversation implementation in Desktop |

This is not a head-to-head performance comparison. No installer, plugin, or source code from those repositories is bundled. [Design notes](docs/DESIGN.md).

## License

[MIT](LICENSE). Independent project; not affiliated with OpenAI or TypeSafe. Provider access and billing remain each user's responsibility.
