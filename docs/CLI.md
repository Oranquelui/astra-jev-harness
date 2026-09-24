# CLI reference

Run from the repository root. Use `python3 "Codex cli/main.py" --help` for the parser; the root `coding.py` remains a compatibility entrypoint without Keychain supplementation.

1. `plan --repo ROOT --task-file TASK --out PLAN`: snapshot eligible tracked files locally, outside the source repository. Above 2 MB or 1,500 eligible files, add reviewed `--focus-file PATH` values and optionally `--scope-max-calls N` (default 4) to bound the local shortlist before Jev. Review retained and `scoped_out` paths in `PLAN.md`; required-file recall is unknown without labels. Preserve existing changes.
2. `run --plan PLAN --out RUN --mode jev --verify-json '["python3","-B","-m","unittest","discover"]'`: select context, generate full-file replacements using your Codex login, and verify an isolated candidate. Adapt the argument-array verification command to your project. Do not pass a shell string. `auto` skips Jev for a small context; an explicit Jev request should use `jev`.
3. Inspect `result.json`, `REPORT.md`, `changes.diff`, and verification output. `verify --run RUN` reruns verification without another model request.
4. `apply --run RUN` applies verified, unchanged edits. It checks source and candidate integrity, refuses collisions at new paths, and leaves edits uncommitted. Inspect `recovery_incomplete` if rollback could not fully complete; do not overwrite concurrent changes.

## Creating files and editing tests

Declare task-authorized changes during planning:

```sh
python3 "Codex cli/main.py" plan --repo /absolute/repo \
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

Jev: at most 24 requests; Astra: at most two generations, the second only for requested files already inside the plan. A `scoped_out` file requires a fresh focused plan. No automatic provider retries. Authentication, transport, schema, and verification failures are distinct from successful implementation. Generated edits and tests need normal review.

For a large repository, CLI bounds the local shortlist to 350,000 source bytes. `run` also checks the serialized worst-case Astra prompt against its separate 500,000-byte limit **before** making a Jev request. If Astra needs a `scoped_out` path, create a fresh plan with that path as `--focus-file`; it cannot be edited from the old plan.

`result.json.selection` includes probabilities, per-file retention reasons, unjudged paths, and source-byte metrics. These are context diagnostics, not security or correctness guarantees. CLI keeps the conservative batch policy; experimental per-file selection belongs to the Desktop helper.

## Evidence, explicit includes and reuse

`plan --include-file`, `run --evidence` and `run --cache-dir` are documented in [EVIDENCE.md](EVIDENCE.md), alongside safe failure diagnostics and `measure.py`. Reuse never grants permission to repeat a failed provider call.
