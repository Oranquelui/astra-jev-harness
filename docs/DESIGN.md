# Design and prior art / 設計と参考

Jev supplies typed relevance judgments; local code owns the workflow. It is not used to grant permissions or declare that a patch is correct.

The current split is deliberate: CLI calls the user's logged-in Codex to generate candidate edits and verify/apply them; Desktop hands selected context to the current conversation. The latter never launches another Codex CLI for generation.

## Selection

A local Git snapshot records eligible tracked files and their hashes. Files are sent whole in bounded batches. Each has an independent Noul relevance question. Probabilities at or below 0.2 are treated as confidently irrelevant; at or above 0.8 as relevant; the middle remains uncertain. These are experimental thresholds.

The default policy keeps the entire batch when anything is uncertain. Experimental `per-file` retains uncertain files without retaining all irrelevant siblings. Unjudged files stay present, resolvable dependencies/configuration/instructions are added, and a global empty selection falls back to all eligible files. Every file has a probability or an explicit unjudged state plus retention reasons.

`compare` replays saved probabilities locally. It reports retained bytes and caller-labeled required-file recall; unlabeled recall is unknown. It neither makes new model calls nor authorizes consumption of stale context.

## What informed the implementation

- [Movez's Jev Engineering post](https://x.com/0xMovez/status/2101007482919227841): separating generation from bounded decisions, current-state checks, explicit budgets, incremental records, and distinguishing selection from action completion.
- [hermes-jev-skills at 655cee2](https://github.com/kerpopule/hermes-jev-skills/tree/655cee2604d5f1896b7ffc4b31254d19a7ac3438): per-candidate judged/unjudged coverage in `jevkit/rerank.py` and comparison before changing policy. Its compaction scorecard reports a configuration that did worse than a simpler baseline; that is why we keep per-file selection experimental rather than promoting it from a smaller-context example alone.
- [jev-lint](https://github.com/mizchi/jev-lint): documentation structured around a concrete problem, short setup, visible usage/data flow, measured results, and explicit limitations. It performs semantic linting, not this project's file-context selection.

These are references, not bundled dependencies or source-code copies. We did not install their agent plugins, routing middleware, or permission classifiers. There is no cross-project speed comparison here.

## 日本語

Jevには関連性という限定された判断を任せ、権限・上限・鮮度・適用条件はコードで扱います。CLIとDesktopの実行方式を分離し、未判定や不確実な情報を勝手に捨てません。参考先の考え方をこの用途に合わせて実装しましたが、外部のinstallerやソースコードを同梱していません。コンテキストが小さくなっただけでは品質・費用改善の証拠にならないため、保存済み応答の比較を用意し、新方式の既定採用は保留しています。
