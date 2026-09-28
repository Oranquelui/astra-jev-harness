# Go migration: correctness, cost and speed

Status: implementation and evaluation of the first compatibility slice. The user approved proceeding with Go on 2026-09-28, prioritizing coding accuracy, cost and speed. This supersedes bundled CPython as the intended migration direction; v0.6.0 remains the supported Python runtime until the replacement passes its gates.

## First working slice

Build `astra-jev-core`, a local JSON-lines executable with no Python or provider dependency. Implement reusable Go primitives for Python import extraction, Python-compatible canonical JSON/request hashes, and byte-bounded original-source views. Use pinned Tree-sitter/Python grammar rather than replacing Python AST analysis with regular expressions. C compilation is a build dependency; do not claim pure-Go cross-compilation or universal OS support.

The executable is an offline compatibility tool, not a replacement for the host's `select/check/present` workflow. It neither reads repositories nor validates saved Jev selections. It must not become a way to bypass freshness, scope, secret filtering or Jev-required checks.

## Acceptance and measurements

- Compare against the existing Python implementation on independently specified edge cases and tracked Python files. Normalize only irrelevant import traversal ordering. Compare canonical bytes/hashes and every excerpt/page field exactly. Syntax disagreement is an explicit failed compatibility case, never evidence that a source has no dependencies.
- Test malformed inputs, Unicode/CRLF, aliases, relative/nested/multiline imports, comments/strings containing fake imports, large integers, floating-point serialization, truncated views, long lines and output budgets. Preserve unavailable/unsupported states explicitly.
- Run the native executable with an empty PATH. Keep Python solely in the development comparison runner; native tests and the binary must run without it.
- Timing is optional and off by default. The user clarified that recurring measurements during coding would waste time/tokens. Only a one-time local migration check uses matched inputs/output obligations; no runtime instrumentation, per-task A/B runs, additional model calls or automatic benchmark are added. Report sample count and timing limits; do not infer end-to-end coding speed or quality from local timing.
- Record live development-selection attempts, completed requests, cache reuse and tokens separately. Migrating the implementation language must not add product API requests or automatic retries. No inference/token/cost reduction is established by this slice.

## Remaining migration after this gate

Port snapshot/path safety, full dependency closure, scoping/chunking, Jev transport/cache/usage, host freshness checks and commands, evidence/output/measurement, CLI generation/apply, and installation. Preserve separate host contracts and the existing result formats. Test failure, cancellation, symlinks, permissions, cost limits and rollback before replacing any entrypoint. Retain the v0.6.0 release as the rollback target.

Cutover requires all supported commands and the installer to work without Python, equivalent regression coverage and supported-platform builds. Verify unchanged model inputs, request counts, budget/failure handling and cache semantics locally. Reuse available execution receipts for cost observations; do not require extra live generations merely to port an unchanged contract. Any later live coding A/B evaluation is a separate explicitly scoped activity, never a routine step in coding. It must use the same tasks, source revisions, model/effort and independent acceptance tests and include all Jev/Astra calls, failures, retries and elapsed time. The active Desktop conversation must not launch a second Codex for generation.

No version bump, public release, global Skill replacement or default selection-policy change is part of the first compatibility slice.

## Build and check this slice

Go 1.26+ and a C compiler are needed to build; Python 3.14 is needed only for the development comparison against v0.6.0, including Python 3.14 syntax fixtures. Users of the compiled core need neither Python nor Go. Tree-sitter and the Python grammar are linked into the executable. Build each OS/CPU artifact and test it there; do not infer cross-platform support from one macOS build.

```sh
go test ./...
go build -trimpath -o /tmp/astra-jev-core ./cmd/astra-jev-core
python3 scripts/compare_native.py --binary /tmp/astra-jev-core --out /tmp/native-comparison.json
```

The last command runs compatibility checks only. Explicit `--samples 3` adds a small local timing check when needed; this is not called by the Skill, the product or normal coding commands. Result files stay outside Git.

Send one JSON object per line to the binary. Operations are `imports` (`source`), `hash` (`value`), `excerpt` (`path`, `text`, `start_line`, `lines`), and `page` (`base`, `items`, `offset`, `max_bytes`). `imports` returns normalized static module/name/relative-level records; it does not implement dependency closure or execute source. Input lines are bounded to 2 MB and Python sources to 100 KB. The first syntax/validation error in a request returns an explicit error; processing continues for subsequent lines and the process exits 2 if any request failed. No source text is printed in error diagnostics.

Go decoding preserves arbitrary JSON integers and the distinction between integer and floating-point tokens for Python-compatible request hashing. Invalid UTF-8, unpaired Unicode surrogates and nonfinite JSON numbers are rejected rather than silently rewritten. The parser is an import extractor, not a complete CPython syntax validator; passing a finite compatibility suite is not a proof of equivalence for all Python programs.

## Local evidence — 2026-09-28

- Existing Python baseline: 199 tests passed; the production Python implementation remains unchanged.
- Native Go unit and protocol tests passed (10 tests), including race-enabled execution; `go vet` passed. The comparison executable ran with an empty PATH and without credentials or a Python/Go executable on PATH. The native CI workflow is prepared but has not been run remotely for this local change.
- First comparison: 1,178 cases matched, including 55 tracked Python files, 15 targeted import cases, 1,010 canonical JSON/hash cases, 63 excerpts and 35 pages. Five cases were rejected by both implementations. Subsequent tracked-file additions increase the fixture count automatically.
- Final correctness-only check: 1,180 cases matched, including the two new reference/comparison scripts. Timing results were empty, verifying that the default performs no repeated timing runs.
- One-time smoke timings only: macOS 26.6.2 arm64, Python 3.14.7, Go 1.27.1, three alternating samples per implementation. Median startup plus one hash: Python 79.591 ms, Go 4.550 ms. Median full matched batch including startup: Python 156.566 ms, Go 96.713 ms. These are small local samples, not a stable performance benchmark or a coding-speed claim. No timing run is triggered by ordinary coding or CI.
- Local binary: 5,414,818 bytes with the build command above. Size is build/platform-specific. This is not a published release artifact.
- Comparison provider calls/tokens: zero. Development-context selection was separate: 6 live attempts, 6 completed, 0 reused, 43,469 input / 483 output Jev tokens. No child Codex generation ran.
- End-to-end coding correctness, total provider cost and coding speed have not been compared. The core has no provider transport, so zero calls here is not a prediction about a complete coding task. Full Python removal is still incomplete.
