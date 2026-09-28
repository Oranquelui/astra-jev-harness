# Go runtime migration

The approved migration replaces the normal Harness runtime with `bin/astra-jev`. The Desktop and Claude Code Skill launchers are POSIX `.sh` wrappers around that executable; they do not start Python, compile code, install a toolchain, benchmark, or compare models during coding. Version 0.7.0 is the native release line. The earlier v0.6.0 tag remains the Python rollback reference.

## Implemented scope

- Repository planning, lexical scoping, complete source-range batching and request budgets; path, symlink, file-size, source-hash, mode, Git HEAD/branch/status and credential guards.
- Tree-sitter Python import extraction, Python package/src-root and JS/TS alias/workspace closure; Go source, go.mod/go.work and local package/module dependency closure. Python syntax uncertainty conservatively retains Python scope. Dynamic imports and arbitrary build configurations remain partial.
- Exact Python-compatible canonical JSON/request hashes, strict Jev response validation, exact-request cache reuse, scoped environment/Keychain credentials, fixed-origin HTTPS transport, no redirects and no automatic retries. Each attempt is saved before a request.
- Separate Desktop/Claude surfaces: plan/select/check/read/present/discover/compare, preserved Jev-required Desktop Skill checks and original-source byte caps.
- Extractive evidence packets; explicitly routed progress-output selection with one child execution, original stderr/exit status, bounded buffering, private stdout archive and full-output fallback on failure. Receipt comparison remains an explicit offline command; missing spend stays unknown.
- CLI configuration read through the user's installed Codex, isolated generation with the configured model/effort, at most one context expansion, candidate verification/reverification and explicit transactional apply. Test/instruction protections, new-file grants, freshness checks and partial rollback reporting are retained. Desktop does not call the CLI generator.
- Native Skill installation with read-only check, idempotence, legacy-link migration and refusal to overwrite another Skill. No user authentication or model configuration is copied or rewritten.

The coherent cutover exceeds the usual small-patch size: context planning, cache serialization, saved handoffs, both host adapters and installation share the same contracts. Splitting their runtime activation would leave mixed interpreters and inconsistent artifact readers. The prior compatibility-core commit remains a separate reviewable checkpoint; Python references are retained for offline regression checking.

## Build, use and rollback

Source builds require Go 1.26+ and a C compiler. The pinned Tree-sitter Python grammar and parser are linked into the executable; Go and Python are not runtime prerequisites. C compilation means this is not a pure-Go cross-compilation promise.

```sh
scripts/build-native.sh
bin/astra-jev --help
bin/astra-jev install --check
bin/astra-jev install
# Claude Code uses its own destination:
bin/astra-jev install --target claude-code --check
```

Platform archives contain `bin/astra-jev`, Skill files, current guides and dependency notices; `.py` scripts and Python caches are excluded. Extract into a permanent directory, verify the archive's SHA-256 against the accompanying checksum, then run `bin/astra-jev install`. Keep that directory while its Skill symlink is installed. macOS arm64 and Linux amd64 are built/tested independently in CI; other platforms require separate verification. No platform is established by a cross-compile alone.

For rollback, keep local edits and run outputs, select the v0.6.0 checkout in a separate directory, and explicitly repoint only the Skill symlink owned by this installation. The installer deliberately refuses to replace an unrelated checkout's link. Old `.py` entrypoints stay in source checkouts for compatibility/development; use Python 3.10+ when deliberately running them. Python 3.14 is required by the full development oracle's 3.14 syntax fixtures. The historical synthetic Python benchmark is a development experiment, not a native production command.

## Native commands

| Previous source entrypoint | Native entrypoint |
|---|---|
| `python3 "Codex Desktop/context.py"` | `bin/astra-jev desktop` |
| `python3 "Claude Code/context.py"` | `bin/astra-jev claude-code` |
| `python3 "Codex cli/main.py"` | `bin/astra-jev cli` |
| `python3 evidence.py` | `bin/astra-jev evidence` |
| `python3 output.py` | `bin/astra-jev output` |
| `python3 measure.py` | `bin/astra-jev measure` |
| `python3 install.py` | `bin/astra-jev install` |

An absolute `bin/astra-jev` path works from another directory. Skill `.sh` launchers resolve the physical checkout behind installed symlinks. Project tests may require Python, Node, Go or another project runtime; that requirement belongs to the explicit test command, not Harness startup. Existing v1/v2 snapshots and receipt shapes are read directly. Hashes are canonical across JSON key ordering; native JSON files may have different whitespace/key order. Decimal cost strings use a normalized exact decimal representation. Go-inclusive snapshots are a native extension and are not readable by the older Python snapshot validator.

## Verification without recurring overhead

```sh
go test ./...
go vet ./...
# Explicit migration-only oracle; synthetic inputs, no provider calls or timing:
ASTRA_JEV_REFERENCE_PYTHON="$(command -v python3)" go test ./internal/harness
go build -trimpath -o /tmp/astra-jev-core ./cmd/astra-jev-core
python3 scripts/compare_native.py --binary /tmp/astra-jev-core --out /tmp/native-compatibility.json
```

The optional `ASTRA_JEV_TEST_GO` test builds a temporary binary and starts it with an empty PATH. CI also builds the real executable and validates the package. Native tests cover cached selections, identical Jev payloads/hashes/decisions, dependency closure, freshness and host boundaries, budget rejection before credentials/output creation, malformed response/cache records, HTTP failure/redirects, evidence tampering, output fallback/streaming/credential isolation, usage unknowns, configured-model CLI runs with fake Codex, explicit apply, occupied destinations and rollback preserving concurrent changes. Race checks use local fixtures only.

The retained Python baseline and first-core reference checks complement these native tests; passing the old Python suite alone is not evidence that the Go port works. No live coding generation or timing comparison is required for the language cutover. Normal execution has no added A/B, benchmark or automatic compilation path.

## Evidence and limits

The first compatibility-core checkpoint had 1,180 matched local cases and 199 passing Python tests. A small optional three-sample startup check was recorded at that earlier checkpoint; it is not an end-to-end speed claim and is not rerun in this migration. Timing defaults to zero in the development comparator.

This runtime migration uses bounded Jev development-context selection separately from tests: 8 attempts, 8 completed, no cache reuse; 61,888 input / 782 output Jev tokens. Test servers and fake Codex executables are local fixtures, not live model evaluations. Complete conversation token use, total provider cost savings, coding quality improvement and task-completion speed have not been measured. Removing interpreter setup/startup is an implementation fact; a numeric coding-speed or savings claim would require a separately authorized evaluation.

## Local verification at runtime cutover (2026-09-29)

- 31 native Go tests passed, including race-enabled execution and `go vet`; migration-only tests used synthetic Python fixtures and fake Codex, not a real generation.
- 199 retained Python tests passed; all 1,181 final core compatibility cases matched, with timing disabled.
- Native-to-Python and Python-to-native plan/selection checks passed. The installed-style `.sh` Skill resolved the correct checkout and rejected no-Jev and stale handoffs.
- The native workflow ran with a PATH containing only Git/dirname and failing traps named python, python3 and go. No interpreter/compiler trap ran, no live provider was called, and no timing sample was taken.
- Platform CI and public release verification are recorded by their GitHub runs; local macOS evidence alone is not Linux evidence.
