# Design and prior art / 設計と参考

Jev supplies typed relevance judgments; local code owns the workflow. It is not used to grant permissions or declare that a patch is correct.

The current split is deliberate: CLI calls the user's logged-in Codex to generate candidate edits and verify/apply them; Desktop hands selected context to the current conversation. The latter never launches another Codex CLI for generation.

## Selection

A local Git snapshot records eligible tracked files and their hashes. Files are sent whole in bounded batches. Each has an independent Noul relevance question. Probabilities at or below 0.2 are treated as confidently irrelevant; at or above 0.8 as relevant; the middle remains uncertain. These are experimental thresholds.

For a repository whose eligible files exceed 2,000,000 bytes or 1,500 files, `plan` first narrows candidates locally by lexical task/file matching. This stage makes no TypeSafe request and keeps full files rather than truncating them. The lexical matcher does not translate Japanese-only tasks; without an ASCII identifier or path, an explicit focus file may be needed. Repeated `--focus-file` paths pin eligible task-critical files; `--scope-max-calls` (default 4, range 1–24) bounds the planned Jev requests for this large-repository scope. Repository instructions, relevant configuration and resolvable dependencies remain in the bounded plan. Desktop's scoped candidate cap is 2,000,000 bytes; CLI uses 350,000 bytes to leave room within its separate 500,000-byte Astra prompt bound. If there is no task/file match and no required path was supplied, or the pinned and required files cannot fit, planning fails instead of silently dropping them. Repositories already within the original bounds follow the existing snapshot path.

The plan distinguishes ineligible/excluded files from eligible files left outside the local scope. `plan['scoped_out']` records each omitted eligible file's hash, byte count and mode; `plan['scope']` records eligible and scoped-out counts/bytes, maximum calls/bytes, and planned calls. A locally omitted file received **no Jev judgment**. CLI may pass Astra at most 512 omitted file names and the total omitted count, but not their contents; it validates the serialized worst-case prompt against its 500,000-byte limit before any Jev call. Scope selection can miss a task-required file, so its measured byte reduction is not evidence of recall or better coding. Independently identified required-file labels are needed to evaluate coverage. The planned request budget and the actual `select`/`run` request budget are separate checks; a plan does not authorize provider calls or edits.

The default policy keeps the entire batch when anything is uncertain. Experimental `per-file` retains uncertain files without retaining all irrelevant siblings. Unjudged files stay present, resolvable dependencies/configuration/instructions are added, and a global empty selection falls back to all eligible files. Every file has a probability or an explicit unjudged state plus retention reasons.

`compare` replays saved probabilities locally. It accepts independently identified required paths from either the recorded plan or `scoped_out`. It reports `scope_required_recall` and `missing_in_scope` for the local shortlist separately from end-to-end `required_recall` after Jev selection. Without caller-provided labels, recall remains unknown. Comparison neither makes new model calls nor authorizes consumption of stale context.

## What informed the implementation

- [TypeSafe's Jev 1.13 jaggedness notes](https://docs.typesafe.ai/model-jaggedness/jev-1.13) explicitly recommend filtering irrelevant state in code before sending it. [Re-ranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe) uses fast retrieval before Jev scores a shortlist and notes that re-ranking cannot recover a correct item absent from that shortlist. [Hierarchical classification](https://docs.typesafe.ai/cookbooks/hierarchical_classification) includes a source-file tree example and keeps multiple plausible paths to reduce early-selection errors. Applying those patterns to multi-file coding context and preserving dependencies is this Harness's design choice, not a TypeSafe-provided 2 MB switch.
- [Movez's Jev Engineering post](https://x.com/0xMovez/status/2101007482919227841): separating generation from bounded decisions, current-state checks, explicit budgets, incremental records, and distinguishing selection from action completion.
- [hermes-jev-skills at 655cee2](https://github.com/kerpopule/hermes-jev-skills/tree/655cee2604d5f1896b7ffc4b31254d19a7ac3438): per-candidate judged/unjudged coverage in `jevkit/rerank.py` and comparison before changing policy. Its compaction scorecard reports a configuration that did worse than a simpler baseline; that is why we keep per-file selection experimental rather than promoting it from a smaller-context example alone.
- [jev-lint](https://github.com/mizchi/jev-lint): documentation structured around a concrete problem, short setup, visible usage/data flow, measured results, and explicit limitations. It performs semantic linting, not this project's file-context selection.

These are references, not bundled dependencies or source-code copies. We did not install their agent plugins, routing middleware, or permission classifiers. There is no cross-project speed comparison here.

## 日本語

Jevには関連性という限定された判断を任せ、権限・上限・鮮度・適用条件はコードで扱います。CLIとDesktopの実行方式を分離し、未判定や不確実な情報を勝手に捨てません。大きなrepoではまず課題に基づくローカル絞り込みを行い、Jevには上限内の候補だけを渡します。絞り込み対象外はJevが「無関係」と判断したファイルではなく、必要ファイルの取りこぼしもあり得ます。公式の段階的検索・再評価の考え方をこの用途に応用しましたが、外部のinstallerやソースコードは同梱していません。コンテキストが小さくなっただけでは品質・費用改善の証拠にならないため、保存済み応答の比較と独立した必要ファイルの確認を用意しています。
