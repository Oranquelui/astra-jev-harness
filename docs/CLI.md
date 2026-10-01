# CLI reference

Run from the repository root. Use `bin/astra-jev cli --help` for the parser; the root `coding.py` remains a compatibility entrypoint without Keychain supplementation.

1. `plan --repo ROOT --task-file TASK --out PLAN`: snapshot eligible tracked files locally, outside the source repository. Above 2 MB or 1,500 eligible files, add reviewed `--focus-file PATH` values and optionally `--scope-max-calls N` (default 4) to bound the local shortlist before Jev. Review retained and `scoped_out` paths in `PLAN.md`; required-file recall is unknown without labels. Preserve existing changes.
2. `run --plan PLAN --out RUN --mode jev --verify-json '["python3","-B","-m","unittest","discover"]'`: select context, generate full-file replacements using your Codex login, and verify an isolated candidate. Adapt the argument-array verification command to your project. Do not pass a shell string. `auto` skips Jev for a small context; an explicit Jev request should use `jev`.
3. Inspect `result.json`, `REPORT.md`, `changes.diff`, and verification output. `verify --run RUN` reruns verification without another model request.
4. `apply --run RUN` applies verified, unchanged edits. It checks source and candidate integrity, refuses collisions at new paths, and leaves edits uncommitted. Inspect `recovery_incomplete` if rollback could not fully complete; do not overwrite concurrent changes.

## Continuing without Jev

Jev is not a prerequisite for all authorized coding work. Honor a user's no-Jev choice for the current task and in-scope follow-ups without asking again. If required scope exceeds planning limits, credentials are unavailable, or Jev fails, stop that operation and state the reason and **“Jev selection unverified / Jev未検証 — continuing without Jev”** once. A successful Jev judgment explicitly required for acceptance remains incomplete; independent authorized work may continue.

**CLI `--mode astra` skips Jev but still invokes Codex generation. It is not an offline mode.** The CLI accepts `auto`, `astra` and `jev`; `local` belongs to the Desktop/Claude context helpers. Use `astra` only when Codex generation and its code transmission are already authorized. A no-Jev choice alone does not authorize a new provider or another coding agent. `auto` can call Jev and does not guarantee no-Jev operation.

With a fresh, sufficient CLI plan and existing generation authority, use a new run directory:

```sh
bin/astra-jev cli run --plan /absolute/plan \
  --out /absolute/new-run-without-jev --mode astra \
  --verify-json '["go", "test", "./..."]'
```

Use the target project's verification command. This route retains all in-plan candidates as unjudged, needs no TypeSafe credential lookup, and preserves Codex configuration, generation and verification requirements. It cannot restore `scoped_out` files or cure a Codex configuration/login failure. Keep the original failed run and partial-attempt receipts; inspect the failure stage before starting another run. Do not automatically retry, overwrite the old result, or relabel it as successful.

If a valid plan cannot cover required files, preserve those files rather than dropping required focus/dependencies or repeatedly increasing caps. Continue investigation, implementation and tests with bounded native tools in the already-running coding session, within its existing authority. Recheck root, branch, HEAD, status, diff and relevant file contents before edits; keep reads focused (prefer 80 lines, at most 200 lines/24 KB). Do not spawn a replacement coding agent from Desktop or Claude Code. Without an authorized active coding session, continue available local preparation, diagnostics and tests; the harness generation remains incomplete. If all new external calls are prohibited, do not run `astra` or `auto`; honor that restriction in the current session as well.

Local continuation keeps secret/path guards, source freshness, artifact integrity and external-action boundaries. Stop failed credential lookups without authentication resets or unrelated secret searches. `run → verify → apply` protections remain unchanged: a manual edit is not a verified harness candidate, failed/unverified candidates cannot be applied, and `verify --run` can rerun saved tests without another model generation. Routine replies report changes, verification and actionable blockers; show usage only on request from saved records, without extra benchmarks or calls.

## Creating files and editing tests

Declare task-authorized changes during planning:

```sh
bin/astra-jev cli plan --repo /absolute/repo \
  --task-file /absolute/task.txt --out /absolute/plan \
  --allow-create src/helper.py \
  --allow-create tests/test_helper.py \
  --allow-test-edit tests/test_existing.py
```

Without flags, existing eligible source files can be edited; existing tests remain protected. New paths must not exist, including ignored files. Paths cannot escape the repository, traverse symlinks, collide by case, or target excluded/instruction files. New files use mode 0644. Existing file modes are preserved. New/edited tests passing is not sufficient evidence that previous behavior is preserved: inspect test changes and retain independent regressions.

## Model, verification, and limits

The generator inherits `model` and `model_reasoning_effort` from Codex CLI's user configuration and trusted project configuration, resolved through the installed CLI's read-only `config/read` API. It does not inherit a Desktop conversation's temporary model selection. If a setting is absent, that setting is left to Codex's default; the harness never substitutes Astra or Medium. Your own Codex login must support the configured model.

Only those two settings are forwarded. Generation retains `--ignore-user-config`, the read-only sandbox and existing runtime isolation flags, so unrelated MCP, plugin, instruction and permission settings are not copied into the generation process. Configuration is read once before Jev selection and reused if more context is requested. Failure stops before any paid selection or generation. Custom model providers and configured legacy profiles are currently rejected rather than silently using a different provider/model; use base model/effort settings with the first-party login. Interactive session-only overrides and `--profile` selection are not inherited.

`result.json` records `model_settings`; generation metadata records `requested_model` and `requested_reasoning`. The exec usage event does not identify the serving model/effort, so `model` and `reasoning` remain null and exact-model cost estimates remain unknown. A requested model is not proof of the model used. No new savings measurement is claimed. The historical benchmark runner retains its explicit Astra/Low configuration.

The configuration reader was checked with Codex CLI 0.153.2 without starting a model turn. These API/runtime flags are version-sensitive. No saved Codex settings or credentials are changed.

The verification command runs through `codex sandbox --permission-profile :read-only`. Dependencies are not installed automatically. Builds requiring generated files or unavailable dependencies can fail independently of the patch. Do not weaken the sandbox or tests to make a candidate pass.

Jev: at most 24 requests; Astra: at most two generations, the second only for requested files already inside the plan. Continuing harness generation with a `scoped_out` file requires a fresh sufficient plan; if required scope cannot fit, use the continuation guidance above. No automatic provider retries. Authentication, transport, schema, and verification failures are distinct from successful implementation. Generated edits and tests need normal review.

For a large repository, CLI bounds the local shortlist to 350,000 source bytes. `run` also checks the serialized worst-case Astra prompt against its separate 500,000-byte limit **before** making a Jev request. To continue harness generation with a needed `scoped_out` path, create a fresh sufficient plan with that path as `--focus-file`; it cannot be edited from the old plan. If the required scope cannot fit, follow Continuing without Jev instead of repeatedly replanning.

`result.json.selection` includes probabilities, per-file retention reasons, unjudged paths, and source-byte metrics. These are context diagnostics, not security or correctness guarantees. CLI keeps the conservative batch policy; experimental per-file selection belongs to the Desktop helper.

## Evidence, explicit includes and reuse

`plan --include-file`, `run --evidence` and `run --cache-dir` are documented in [EVIDENCE.md](EVIDENCE.md), alongside safe failure diagnostics and `measure.py`. Reuse never grants permission to repeat a failed provider call.
