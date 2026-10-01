# Local continuation when Jev is not used

Jev supplies relevance judgments; it is not an authorization service for coding. Continue investigation, implementation and tests already authorized by the user when they choose local work or the Jev stage cannot proceed. Do not ask for the same local permission again. Keep that choice for the current task and its in-scope follow-ups until the user changes it. New external actions, protected operations or material scope changes still need their own authority.

At the transition, say **“Jev selection unverified / Jev未検証 — continuing locally”** with the reason once. Distinguish partial/cached judgments from newly read, unjudged files. Do not claim a Jev-selected handoff, measured savings, or completion of an explicitly required Jev acceptance check. Report implementation and test results separately. Do not restore routine call/token reporting.

## Choose by the actual blocker

| Situation | Continue within the existing task scope |
|---|---|
| User chooses no Jev, local work or no external calls | Honor the choice immediately. Do not run Jev planning or credential checks merely to satisfy this Skill. Use a sufficient existing plan if useful, or bounded native reads. |
| `Required scope exceeds budget`, required dependencies exceed snapshot/request bounds, or required files are `scoped_out` | Stop the affected planning/selection step. Preserve required paths. Use bounded native reads for the real scope. Do not drop required focus/dependencies, raise caps repeatedly, or call a smaller incomplete plan a complete solution. |
| Missing/unavailable credentials or Keychain denial/timeout | Stop credential lookup and new Jev requests. Do not repeatedly run `doctor`, search unrelated `.env` files, print credentials or reset authentication. A timeout does not prove absence. Continue locally. |
| Provider/network failure, timeout or invalid response | Preserve the failure and partial-attempt receipts. Do not retry automatically: an attempt may have reached the provider. Do not mutate the failed selection into local success. Continue with a fresh local selection if its plan is sufficient, or bounded native reads. |
| User explicitly requires a successful Jev judgment as an acceptance condition | Keep that condition incomplete and explain the blocker. Continue independent local work that is already authorized; do not declare the whole request complete without its required evidence. |
| Material checkout mismatch, stale/tampered artifact, secret/protected data, or missing action authority | Resolve the actual safety/permission issue. Local continuation does not waive these checks. |

The local workflow is not limited to an offline comparison. A blocked Jev step does not require an extra permission round for work the user has already authorized. Never use `auto` for an offline guarantee: it may make provider calls. Do not return from a chosen local workflow to Jev merely because code changed. A later Jev attempt requires current authorization, a resolved cause and inspection of any existing attempt record; do not add automatic retries.

## A. A valid plan covers the required files

Use the associated Harness checkout's **direct executable** for every command below. The Skill's `scripts/context.sh` deliberately adds `--require-jev` to select/check/read and will reject this path. Leave that guard intact.

```sh
"<absolute-harness-root>/bin/astra-jev" desktop select \
  --plan <fresh-sufficient-plan> --out <new-local-selection-outside-target> \
  --mode local --max-calls 1
"<absolute-harness-root>/bin/astra-jev" desktop check \
  --selection <new-local-selection-outside-target>
"<absolute-harness-root>/bin/astra-jev" desktop read \
  --selection <new-local-selection-outside-target> \
  --path <required-relative-source-path> --start-line 1 --end-line 80
```

`--mode local` makes no provider call or credential lookup. It retains all files **already in the plan** as unjudged; it does not restore `scoped_out` or excluded files. A successful local `check` verifies freshness/integrity, not Jev relevance or implementation correctness. Keep new output directories outside the target repository and preserve prior failure records. Do not dump `plan.json` or full `context.json` into the conversation.

Use direct `read` with its existing line/byte limits. **Do not use `present` for local selections**: it requires valid Jev judgments even through the direct helper. If the plan is stale, incomplete or cannot be recreated within bounds, use path B for authorized work rather than falsifying hashes or weakening limits.

## B. No adequate plan is available

Local selection cannot repair a planning-budget failure: both routes depend on the same bounded snapshot. A plan created by dropping an essential runtime/provider file does not cover that file, even if `plan` succeeded. Keep task-required and excluded/scoped-out paths distinct.

1. Confirm the exact target root, branch/HEAD, applicable repository instructions and existing status/diff. Do not change another checkout or assume the saved plan's HEAD is current.
2. Use native file tools for a focused path/symbol search and read only necessary source ranges. Prefer 80 lines at a time; keep each excerpt within 200 lines / 24 KB. Narrow overlarge results instead of dumping files, snapshots or the full repository into the conversation.
3. Inspect the real required implementation files, tests, instructions and dependency boundaries. Preserve uncertainty; a local search is not a Jev judgment. Do not trust a shortlist that omits a known required file.
4. Keep reads inside the authorized repository. Resolve unexpected symlinks and paths before reading. Do not include credentials, unrelated environment files, customer data or generated dumps. Local processing does not authorize sending source to a provider, forwarding secrets, or copying artifacts into Git.
5. Before editing, recheck current content and relevant Git status/diff, preserving existing changes. Respect protected files and existing edit/test authority. This path has no Harness freshness receipt: perform these checks with native tools and do not claim `check` verified it.
6. Implement and run proportionate tests with the active conversation's normal tools. Do not spawn a second Codex CLI for generation, rebuild the Harness, run benchmarks or call Jev just to prove that local continuation worked. Resume Jev only under the workflow-choice rules above.

## Verification scenarios

- A user says “continue this task without Jev”; the next in-scope turn continues locally without another approval or mandatory plan.
- Required runtime/provider dependencies exceed the planning budget; the actual files remain in the investigation scope and are read in bounded ranges. A smaller successful plan is not presented as covering them.
- Credentials fail before a usable selection; authorized local edits/tests continue without credential retries or secret exposure.
- A provider attempt fails after sending; its failure receipt remains intact, and local continuation uses a separate output or native reads with no automatic retry.
- A sufficient local plan passes direct select/check/read without credentials, remains unjudged, and is still rejected by the Jev-only wrapper and `present`. Source changes still fail the old plan's freshness check.

These scenarios validate workflow handling and existing command boundaries. They do not establish improved model performance, reduced cost or faster task completion.
