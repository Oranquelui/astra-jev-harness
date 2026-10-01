# Bounded source presentation and staged discovery

Implemented for Desktop and Claude Code helpers. These local views add no API calls, retry, credential lookup or retained-context mutation. The CLI generation/apply workflow is unchanged.

## Present retained context (J1)

After `plan → select --mode jev → check`, request a bounded first page:

```sh
"Codex Desktop/skills/astra-jev-coding/scripts/context.sh" present \
  --selection /absolute/selection --max-bytes 8192 --lines-per-file 12
```

`present` requires successful live or cached Jev judgments and checks the host surface, source freshness and artifact hashes before and after rendering. It returns original source, SHA-256, one-based line ranges and explicit `unpresented_ranges`. Instructions appear first, then focus paths, then saved relevance scores. Within other files, the strongest saved source range determines the first line; the local code copies the text. This ordering is a reading aid, not a new omission policy or calibrated whole-file score.

The **entire serialized JSON response including its final newline** fits `--max-bytes` (1,024–24,000, default 8,192). Original full files stay in `context.json`. `next_offset` pages through further files; `read --path … --start-line … --end-line …` retrieves missing ranges. An oversized line becomes an empty excerpt with an explicit reading lead; it is never silently sliced. A metadata entry that cannot fit is refused. Smaller presentation bytes do not establish reduced tokens or cost, and important material may remain unpresented.

## Discover outside the initial shortlist (J2)

A plan can omit eligible files before any Jev judgment. Browse those files locally:

```sh
"Codex Desktop/skills/astra-jev-coding/scripts/context.sh" discover --plan /absolute/plan
"Codex Desktop/skills/astra-jev-coding/scripts/context.sh" discover \
  --plan /absolute/plan --directory src/another-component --max-bytes 8192
```

The first view lists every scoped-out parent directory across pages. Choose an exact directory from that index for short original previews (default four lines per file). `next_offset` pages through the remaining branches/files; there is no permanently discarded top-k branch. Excluded secrets, unsupported files and implicitly untracked files do not enter this index. Freshness covers both included and scoped-out files; preview contents are checked against the saved hash and secret rules again.

Previews are explicitly **unjudged**, not Jev-selected context or edit authorization. Preserve existing focus paths and explicit includes when creating a **new** plan with discovered `--focus-file` paths. On the Jev path, review that plan's scope/budget, then use the normal bounded `select → check` before consuming the new implementation context. For Codex Desktop local continuation, follow the [local guide](../Codex%20Desktop/skills/astra-jev-coding/references/local-continuation.md) instead: inspect required files through bounded native reads when they cannot fit, and do not treat the old plan as complete. `present` still requires Jev judgments; use direct `read` for a valid local selection. No automatic continuation, changed default scope, shared task budget or provider retry is introduced. All previous failed/live spending still counts when considering more requests.

This is an operator-guided directory → preview → focused plan → Jev → source workflow. It does not claim automatic semantic branch discovery: unrelated names and uninformative first lines can still require additional investigation. Keep unexplored pages and budget-limited files distinct from judged irrelevance. The same commands work via `Claude Code/context.py` with that surface's own artifacts.

## Evaluation and limits

Regression fixtures verify exact Unicode/CRLF source, long-line leads, complete pagination, output-byte limits, focus preservation during replanning, two independent unexplored branches, secret exclusion, stale sources, artifact tampering, wrong surfaces and Jev-required rejection. A necessary file deliberately outside the first shortlist can be discovered and focused; this checks the mechanism, not general retrieval accuracy.

Saved-selection presentation can be measured offline as historical replay, but that does not grant permission to consume stale sources for edits. Coding correctness, rereads, end-to-end elapsed time and total Astra + Jev cost need matched repeated coding tasks with independent acceptance labels. No token/cost saving is inferred from the presentation-byte cap.

J3–J5 remain deferred: the current checks do not show a need for new cause/reference questions, syntax-aware extraction, retry/partial-success semantics or new batch/cache defaults. Reconsider them only with measured missed files, repeated reads or provider-cost evidence.

## 日本語

- J1の`present`は保持済み全文を変えず、原文・hash・行番号・未提示範囲を指定JSON出力bytes内で返します。Jev判定・鮮度・surfaceの確認が必須です。
- J2の`discover`は候補外をディレクトリ一覧→短い原文previewへ段階的に確認します。全ページを辿れ、未知の枝を永久に切り捨てません。秘密除外を維持し、previewは「未判定」です。
- Jev経路では発見したパスを既存focus/includeを維持した新しいplanへ追加し、select/checkへ戻します。Desktopのローカル継続では、必須範囲が収まらない場合に通常の範囲読み取りで補い、Jev未検証とします。localで`present`は使いません。自動追加API、retry、選別成功の偽装はありません。
- 出力bytes、必要ファイル発見、品質、会話token、総費用を別々に評価します。現時点でAstra token・総費用の削減率は未測定です。
